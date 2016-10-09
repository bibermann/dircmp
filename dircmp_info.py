#!/usr/bin/env python

import os
import argparse
import json
import sys
import re

def indexDirectory( directory ):
    index = {}
    for filename in directory:
        fileId = directory[filename]
        index[fileId['path']] = fileId
        index.update( indexDirectory( fileId['children'] ) )
    return index

def printIndexResult( index ):
    print( '%i files (%f GiB) and %i folders (%i non-empty) found.' % (
        sum( not index[s]['isDir'] for s in index ),
        sum( index[s]['size'] for s in index )/1024.0/1024.0/1024.0,
        sum( index[s]['isDir'] for s in index ),
        sum( index[s]['isDir'] and bool( index[s]['children'] ) for s in index ),
        ) )

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument( 'path', help = 'json file' )
    parser.add_argument( '--find', help = 'find paths (regex match)' )
    args = parser.parse_args()

    root = os.path.abspath( args.path.replace( '\\', '/' ) )
    if os.path.isfile( root ):
        print( "loading %s..." % root )
        with open( root, 'r' ) as infile:
            directory = json.load( infile )
    else:
        print( "Error: %s is not a file." % root )
        sys.exit( 1 )

    index = indexDirectory( directory )
    printIndexResult( index )

    firstEntry = directory[list(directory.keys())[0]]
    commonRootLen = len( firstEntry['path'] ) - len( firstEntry['name'] )

    print( 'root: %s' % firstEntry['path'][:commonRootLen-1] )

    if args.find:
        print( "searching %s..." % args.find )
        regex = re.compile( args.find )
        findings = []
        for path in index:
            fileId = index[path]
            if regex.search( fileId['path'] ):
                findings.append( fileId )
        findings = sorted( findings, key = lambda s: s['path'].lower() )
        print( "results:" )
        for finding in findings:
            print( finding['path'][commonRootLen:] + ('/' if finding['isDir'] else '') )

if __name__ == "__main__":
    main()