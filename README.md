A small script for converting a Square Space website export to a hugo website.

It's a bit of a kludge, but might be of use to someone somewhere. I used it to migrate a couple of squarespace sites I had to hugo successfully.

Note if you re-run it it'll not redownload images etc, but it will happily overwrite any changes you made to the markdown/frontmatter.

Usage (one you have pip installed the requirements):

```
$ hugo new site blah
$ cd blah
$ python3 squaremigrate.py SquareSpace-Export.xml
```


