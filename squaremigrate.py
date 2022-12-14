#!/usr/bin/env python3

import datetime
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

import html2markdown
import rfc3339

tree = ET.parse(sys.argv[1])
root = tree.getroot()
items = root.findall('channel/item')

namespaces = {
    'wp': "http://wordpress.org/export/1.2/",
    'content': "http://purl.org/rss/1.0/modules/content/"
}

ATTRIB_KEEP_LIST = ['href']
def recursivelyStripMostAttributes(node):
    for key in [x for x in node.attrib]:
        if key not in ATTRIB_KEEP_LIST:
            del(node.attrib[key])
    for child in node:
        recursivelyStripMostAttributes(child)

# First we want to do a scan for attachments, as they can appear after the item they're referenced
# from
attachments = {}
for item in items:
    try:
        type = item.find('wp:post_type', namespaces=namespaces).text
        if type != "attachment":
            continue
        post_id = item.find('wp:post_id', namespaces=namespaces).text
        url = item.find('link').text
        attachments[post_id] = url
    except:
        continue 
    

# now do the actual bits we're interested in
for item in items:
    try:
        type = item.find('wp:post_type', namespaces=namespaces).text
    except:
        continue
    if type == "attachment":
        continue

    link = item.find('link').text
    status = item.find('wp:status', namespaces=namespaces).text
    if status != 'publish':
        print(f'skipping unpublished article {link}')
        continue

    pubdate = item.find('pubDate').text
    date = datetime.datetime.strptime(pubdate, '%a, %d %b %Y %H:%M:%S %z')

    title = item.find('title').text
    original_url = item.find('wp:post_name', namespaces=namespaces).text 
    post_name = original_url.split('/')[-1]
    original_link = item.find('link').text
    
    
    prefix = 'blog/' if type == 'post' else ''
    location = f'{prefix}{original_url}'
    
    if os.path.exists(f'content/{location}/index.md'):
        continue
    
    # Is there a specific thumbnail for this post?
    image_url_list = []
    thumbnail = None
    
    meta = item.find('wp:postmeta', namespaces=namespaces)
    if meta:
        meta_key = meta.find('wp:meta_key', namespaces=namespaces).text
        if meta_key == '_thumbnail_id':
            meta_value = meta.find('wp:meta_value', namespaces=namespaces).text
            attachment_id = meta_value
            thumbnail = attachments[attachment_id]
            image_url_list.append(thumbnail)
        else:
            print(f'Unknown meta key: {meta_key}')

    tags = [x.text for x in item.findall('category')]

    body_html = item.find('content:encoded', namespaces=namespaces).text

    # strip br tags
    body_html = body_html.replace('<br>', '</p><p>').replace('&nbsp;', ' ').\
        replace('<li><p style="white-space: pre-wrap;">', '<li>').\
        replace('<li><p class="" style="white-space:pre-wrap;">', '<li>').\
        replace('</p></li>', '</li>').\
        replace('data-animation-override', '').\
        replace('data-dynamic-strings', '').\
        replace('novalidate', '').\
        replace('xlink:', '').\
        replace('script async defer', 'script')
        
    # This is a more complex one to get youtube videos into a tag. Not all iframes will break
    # ElementTree, but given some do we might as well replace all of them we can
    embedly_re = re.compile('<iframe.*src=.*watch%3Fv%3D([a-zA-Z0-9]+)&.*\/iframe>')
    direct_re = re.compile('<iframe.*src=.*embed\/([a-zA-Z0-9]+)\?.*\/iframe>', re.MULTILINE)
    for expr in [embedly_re, direct_re]:
        body_html = re.sub(expr, r'{{ youtube \1 }}', body_html)

    try:
        doctree = ET.fromstring(f'<root>{body_html}</root>')
    except ET.ParseError as e:
        lines = body_html.split('\n')
        print(f'Error in {link}')
        print(f'{lines[e.position[0] - 1][:e.position[1] + 10]}')
        print("".join([' '] * e.position[1]) + '^')
        raise
    
    body = ""
    pre_builder = ""
    for node in doctree:
        
        # squarespace sometimes breaks up code blocks into blocks per line
        # so this is to try undo that
        if node.tag != "pre" and pre_builder:
            body += f'{{{{< highlight fixup >}}}}\n{pre_builder}{{{{< /highlight >}}}}\n\n'
            pre_builder = ""
        
        if node.tag in ['p', 'ul', 'ol']:
            recursivelyStripMostAttributes(node)
            para = ET.tostring(node)
            body += html2markdown.convert(para)
            body += "\n\n"
            
        elif node.tag == "hr":
            body += "---\n\n"

        elif node.tag == "div":
            noscripts = [x for x in node.iter('noscript')]
            if len(noscripts) >= 1:
                for noscript in noscripts:
                    imgnode = noscript.find('img')
                    url = imgnode.attrib['src']
                    image_url_list.append(url)
                    filename = url.split('/')[-1].replace('+', '_').replace('%', '_')
                    body += f'{{{{< figure {filename} >}}}}\n\n'
            else:
                for child in node:
                    if child.tag == 'img':
                        url = imgnode.attrib['src']
                        image_url_list.append(url)
                        filename = url.split('/')[-1].replace('+', '_').replace('%', '_')
                        body += f'{{{{< figure {filename} >}}}}\n\n'
                    else:
                        print(f"*** {node}")
                        

        elif node.tag == "pre":
            if len(node.getchildren()) > 0:
                for child in node.getchildren():
                    assert child.tag == 'code'
                    pre_builder += f'{child.text}\n'
            else:
                pre_builder += f'{node.text}\n'
        elif node.tag == 'h1':
            body += f'# {node.text}\n\n'
        elif node.tag == "h2":
            body += f'## {node.text}\n\n'
        elif node.tag == "h3":
            body += f'### {node.text}\n\n'
        elif node.tag == "blockquote":
            body += f'> {node.text}\n\n'
        elif node.tag == "iframe":
            try:
                body +=  ET.tostring(node)
            except TypeError:
                body += ET.tostring(node).decode('utf8')
        else:
            print('***', node.tag, node.text)

    try:
        subprocess.run(['hugo', 'new', f'{location}/index.md'], check=True)
    except:
        pass
    
    if thumbnail is None:
        try:
            thumbnail = image_url_list[0]
        except IndexError:
            pass

    with open(f'content/{location}/index.md', 'w') as f:
        f.write(f"""
---
title: "{title}"
date: "{rfc3339.rfc3339(date)}"
draft: false
""")
        if tags:
            f.write("tags:\n")
            for tag in tags:
                f.write(f"- {tag}\n")
        
        if location != original_link[1:]:
            print(location, original_link)
            f.write(f'aliases:\n- {original_link}\n')
            
        if thumbnail:
            filename = thumbnail.split('/')[-1].replace('+', '_').replace('%', '_')
            f.write(f'titleimage: {filename}\n')

        f.write("---\n")
        f.write(body)
        
    for url in image_url_list:
        filename = url.split('/')[-1].replace('+', '_').replace('%', '_')
        target_path = f'content/{location}/{filename}'
        try:
            os.stat(target_path)
        except OSError:
            for _ in range(5):
                try:
                    urllib.request.urlretrieve(url, target_path)
                except urllib.error.HTTPError:
                    # We see a lot of HTTP 504s on Flickr, so just wait a moment and retry
                    time.sleep(0.5)
                except:
                    raise
