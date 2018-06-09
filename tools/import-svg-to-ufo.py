#!/usr/bin/env python
"""
Convert SVG paths to UFO glyphs and that to a UFO font
Author: Santhosh Thottingal <santhosh.thottingal@gmail.com>
Copyright 2018, MIT License
"""

from __future__ import print_function, absolute_import

__requires__ = ["FontTools", "ufoLib"]

from fontTools.misc.py23 import SimpleNamespace
from fontTools.svgLib import SVGPath
from ufoLib import UFOReader, UFOWriter, writePlistAtomically, UFOLibError
from ufoLib.pointPen import SegmentToPointPen
from ufoLib.glifLib import writeGlyphToString
from ufoLib.plistlib import readPlist
import argparse
import os


class InfoObject(object):
    pass


def parseSvg(path):
    import xml.etree.ElementTree as etree
    tree = etree.parse(path)
    return tree.getroot()


def getConfig(configFile):
    import yaml
    with open(configFile, 'r') as ymlfile:
        cfg = yaml.load(ymlfile)
    return cfg


def split(arg):
    return arg.replace(",", " ").split()


def svg2glif(svg, name, width=0, height=0, unicodes=None, transform=None,
             version=2):
    """ Convert an SVG outline to a UFO glyph with given 'name', advance
    'width' and 'height' (int), and 'unicodes' (list of int).
    Return the resulting string in GLIF format (default: version 2).
    If 'transform' is provided, apply a transformation matrix before the
    conversion (must be tuple of 6 floats, or a FontTools Transform object).
    """
    glyph = SimpleNamespace(width=width, height=height, unicodes=unicodes)
    outline = SVGPath.fromstring(svg, transform=transform)

    # writeGlyphToString takes a callable (usually a glyph's drawPoints
    # method) that accepts a PointPen, however SVGPath currently only has
    # a draw method that accepts a segment pen. We need to wrap the call
    # with a converter pen.
    def drawPoints(pointPen):
        pen = SegmentToPointPen(pointPen)
        outline.draw(pen)

    return writeGlyphToString(name,
                              glyphObject=glyph,
                              drawPointsFunc=drawPoints,
                              formatVersion=version)


def transform_list(arg):
    try:
        return [float(n) for n in split(arg)]
    except ValueError:
        msg = "Invalid transformation matrix: %r" % arg
        raise argparse.ArgumentTypeError(msg)


def unicode_hex_list(arg):
    try:
        return [int(unihex, 16) for unihex in split(arg)]
    except ValueError:
        msg = "Invalid unicode hexadecimal value: %r" % arg
        raise argparse.ArgumentTypeError(msg)


def parse_args(args):
    parser = argparse.ArgumentParser(
        description="Convert SVG outlines to UFO glyphs (.glif)")
    parser.add_argument(
        "infile", metavar="INPUT.svg", help="Input SVG file containing "
        '<path> elements with "d" attributes.')
    parser.add_argument(
        "outfile", metavar="OUTPUT.glif", help="Output GLIF file (default: "
        "print to stdout)", nargs='?')
    parser.add_argument(
        "-c", "--config", help="The yaml configuration file containing the svg "
        "to glif mapping", type=str, default="sources/svg-glif-mapping.yaml")
    return parser.parse_args(args)


def main(args=None):
    from io import open

    options = parse_args(args)
    config = getConfig(options.config)
    svg_file = options.infile

    # Parse SVG to read the width, height attributes defined in it
    svgObj = parseSvg(svg_file)
    width = float(svgObj.attrib['width'].replace("px", " "))
    height = float(svgObj.attrib['height'].replace("px", " "))
    name = os.path.splitext(os.path.basename(svg_file))[0]
    ufo_font_path = config['font']['ufo']
    # Get the font metadata from UFO
    reader = UFOReader(ufo_font_path)
    writer = UFOWriter(ufo_font_path)

    infoObject = InfoObject()
    reader.readInfo(infoObject)
    familyName = getattr(infoObject, 'familyName')

    with open(svg_file, "r", encoding="utf-8") as f:
        svg = f.read()

    # Get the configuration for this svg
    try:
        svg_config = config['svgs'][name]
    except KeyError:
        print("\033[93mSkip: Configuration not found for svg : %r\033[0m" % name)
        return
    if 'unicode' in svg_config:
        unicodeVal = unicode_hex_list(svg_config['unicode'])
    else:
        unicodeVal = None
    glyphWidth = width + int(svg_config['left']) + int(svg_config['right'])

    contentsPlistPath = ufo_font_path + '/glyphs/contents.plist'
    try:
        with open(contentsPlistPath, "rb") as f:
            contentsPlist = readPlist(f)
    except:
        raise UFOLibError("The file %s could not be read." % contentsPlistPath)

    glyph_name = svg_config['glyph_name']
    if glyph_name in contentsPlist:
        existing_glyph = True
    else:
        existing_glyph = False

    # Calculate the transformation to do
    transform = transform_list(config['font']['transform'])
    base = 0
    if 'base' in svg_config:
        base=int(svg_config['base'])
    transform[4] += int(svg_config['left'])  # X offset = left bearing
    transform[5] += height + base # Y offset

    glif = svg2glif(svg,
                    name=svg_config['glyph_name'],
                    width=glyphWidth,
                    height=getattr(infoObject, 'unitsPerEm'),
                    unicodes=unicodeVal,
                    transform=transform,
                    version=config['font']['version'])

    if options.outfile is None:
        output_file = ufo_font_path + '/glyphs/' + svg_config['glyph_name'] + '.glif'
    else:
        output_file = options.outfile
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(glif)

    print("\033[94m[%s]\033[0m \033[92mConvert\033[0m %s -> %s \033[92m✔️\033[0m" %
          (familyName, name, output_file))

    # If this is a new glyph, add it to the UFO/glyphs/contents.plist
    if not existing_glyph:
        contentsPlist[glyph_name] = glyph_name + '.glif'
        writePlistAtomically(contentsPlist, contentsPlistPath)
        print("\033[94m[%s]\033[0m \033[92mAdd\033[0m %s -> %s \033[92m✔️\033[0m" %
              (familyName, glyph_name, glyph_name + '.glif'))
        lib_obj = reader.readLib()
        lib_obj['public.glyphOrder'].append(glyph_name)
        writer.writeLib(lib_obj)

if __name__ == "__main__":
    import sys
    sys.exit(main())
