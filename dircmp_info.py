#!/usr/bin/env python

import dircmp_scan
import os
import argparse
import json
import sys
import re
import time

def formatMemory( bytes ):
    units = [ 'Byte', 'KiB', 'MiB', 'GiB', 'TiB' ]
    iUnit = 0
    memory = bytes
    while memory >= 1024.0 and iUnit + 1 < len( units ):
        memory /= 1024.0
        iUnit += 1
    return ('%.0f %s' if iUnit == 0 else '%.2f %s') % (memory, units[iUnit])

def indexDirectory( directory ):
    index = {}
    for filename in directory:
        fileId = directory[filename]
        index[fileId['path']] = fileId
        index.update( indexDirectory( fileId['children'] ) )
    return index

def printIndexResult( index ):
    print( '%i files (%s) and %i folders (%i non-empty) found.' % (
        sum( not index[s]['isDir'] for s in index ),
        formatMemory( sum( (index[s]['size'] if not index[s]['isDir'] else 0) for s in index ) ),
        sum( index[s]['isDir'] for s in index ),
        sum( index[s]['isDir'] and bool( index[s]['children'] ) for s in index ),
        ) )

def calculateDirectorySizes( directory ):
    size = 0
    for name in directory:
        fileId = directory[name]
        if fileId['isDir']:
            fileId['size'] = calculateDirectorySizes( fileId['children'] )
        size += fileId['size']
    return size

def main():
    color_green = '\033[92m'
    color_red   = '\033[91m'
    color_blue = '\033[94m'
    color_brown = '\033[0;33m'
    color_end   = '\033[0m'

    parser = argparse.ArgumentParser()
    parser.add_argument( 'path', help = 'directory or json file' )
    parser.add_argument( '--find', help = 'find paths (regex match)' )
    args = parser.parse_args()

    root = os.path.abspath( args.path.replace( '\\', '/' ) )
    if os.path.isdir( root ):
        print( "scanning %s..." % root )
        directory = dircmp_scan.scanIntoMemory( root, [], [] )
    elif os.path.isfile( root ):
        print( "loading %s..." % root )
        with open( root, 'r' ) as infile:
            directory = json.load( infile )
    else:
        print( "Error: %s does not exist." % root )
        sys.exit( 1 )

    print( 'calculating directory sizes...' )
    calculateDirectorySizes( directory )

    index = indexDirectory( directory )
    printIndexResult( index )

    firstEntry = directory[list(directory.keys())[0]]
    commonRootLen = len( firstEntry['path'] ) - len( firstEntry['name'] )

    print( 'root: %s' % firstEntry['path'][:commonRootLen-1] )

    if args.find:
        print( "searching %s..." % args.find )
        lastOutput = time.time()
        counter = 0
        regex = re.compile( args.find )
        findings = []
        for path in index:
            fileId = index[path]
            match = regex.search( fileId['path'] )
            if match:
                groups = []
                groupCount =  len( match.groups() )
                for i in range( 1, groupCount+1 ):
                    if match.start(i) != -1:
                        groups.append( match.span(i) )
                if not groups:
                    groups.append( match.span() )
                findings.append( (fileId, groups) )

            counter += 1
            if time.time() - lastOutput > 10:
                print( '%i/%i...' % (counter, len(index)) )
                lastOutput = time.time()
        findings = sorted( findings, key = lambda s: s[0]['path'].lower() )
        print( "results:" )
        directoriesFound = []
        for finding in findings:
            fileId = finding[0]
            groups = finding[1]
            path = fileId['path']

            if fileId['isDir']: directoriesFound.append( path + '/' )

            normalColor = color_brown if fileId['isDir'] else color_blue
            text = ''
            if groups[0][0] == 0 and groups[0][1] == len( path ): # match everything -> do not colorize
                index = commonRootLen
            else:
                firstGroupIndex = groups[0][0]
                index = 0 if firstGroupIndex < commonRootLen else commonRootLen
                for group in groups:
                    if index < group[0]: text += normalColor + path[index:group[0]] + color_end
                    text += color_green + path[group[0]:group[1]] + color_end
                    index = group[1]
            text += normalColor
            if index < len(path): text += path[index:]
            if fileId['isDir']: text += '/'
            text += color_end
            print( '%s (%s)' % (text, formatMemory( fileId['size'] )) )
        print( "%s%i%s results found (%i files, %i directories)." % (color_red, len(findings), color_end, len(findings)-len(directoriesFound), len(directoriesFound)) )
        print( "calculating size..." )
        size_all = 0
        size_files = 0
        for finding in findings:
            fileId = finding[0]
            path = fileId['path']
            alreadyIncluded = False
            for d in directoriesFound:
                if path[:len(d)] == d:
                    alreadyIncluded = True
                    break
            if not fileId['isDir']:
                size_files += fileId['size']
            if not alreadyIncluded:
                size_all += fileId['size']
        print( "total size: %s%s%s" % (color_red, formatMemory( size_all ), color_end) )
        if size_all != size_files:
            print( "files only: %s%s%s" % (color_red, formatMemory( size_files ), color_end) )

if __name__ == "__main__":
    main()