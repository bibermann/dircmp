#!/usr/bin/env python

import os
import stat
import time
import argparse
import json
import sys

def getFileId( root, filename ):
    path = os.path.join( root, filename )
    try:
        info = os.stat( path )
    except OSError:
        print( 'Could not access %s' % path )
        return {
            'name' : filename,
            'path' : path,
            'isDir' : False,
            'modified' : 0,
            'size' : 0
            }
    return {
        'name' : filename,
        'path' : path,
        'isDir' : stat.S_ISDIR( info.st_mode ),
        'modified' : info.st_mtime,
        'size' : info.st_size
        }

def isIncluded( fileId, includes ):
    if fileId['path'] in includes:
        return True
    for include in includes:
        if fileId['isDir'] and fileId['path'] + '/' == include[:len(fileId['path'])+1]: # parent dir of include
            return True
        if include + '/' == fileId['path'][:len(include)+1]: # child of include
            return True
    return False

def scanIntoMemory( root, onlyScan, skipScan ):
    progress = {}
    progress['lastOutput'] = time.time()
    progress['counter'] = 0
    return _scanIntoMemory( root, onlyScan, skipScan, progress )

def _scanIntoMemory( root, onlyScan, skipScan, progress ):
    directory = {}
    try:
        dirlist = os.listdir( root )
    except OSError:
        print( 'Could not access %s' % root )
        return directory
    for filename in dirlist:
        fileId = getFileId( root, filename )
        if fileId['path'] in skipScan or (onlyScan and not isIncluded( fileId, onlyScan )):
            continue
        fileId['children'] = {}
        if fileId['isDir']:
            fileId['children'] = _scanIntoMemory( fileId['path'], onlyScan, skipScan, progress )
        directory[filename] = fileId

        progress['counter'] += 1
        if time.time() - progress['lastOutput'] > 10:
            print( '%i...' % progress['counter'] )
            progress['lastOutput'] = time.time()

    return directory

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument( 'path', help = 'directory' )
    parser.add_argument( '--only', action = 'append', help = 'include paths (exact match)' )
    parser.add_argument( '--skip', action = 'append', help = 'exclude paths (exact match)' )
    parser.add_argument( '--save', default = 'scan.json', help = 'default: %(default)s' )
    args = parser.parse_args()

    if args.only:
        onlyScan = set( map( lambda x: os.path.abspath( x.replace( '\\', '/' ) ), args.only ) )
    else:
        onlyScan = set()

    if args.skip:
        skipScan = set( map( lambda x: os.path.abspath( x.replace( '\\', '/' ) ), args.skip ) )
    else:
        skipScan = set()

    if onlyScan & skipScan:
        print( "Error: include and exclude lists have common items." )
        sys.exit( 1 )

    root = os.path.abspath( args.path.replace( '\\', '/' ) )
    if os.path.isdir( root ):
        print( "scanning %s..." % root )
        directory = scanIntoMemory( root, onlyScan, skipScan )
        with open( args.save, 'w' ) as outfile:
            json.dump( directory, outfile, indent = 4 )
    else:
        print( "Error: %s is not a directory." % root )
        sys.exit( 1 )

if __name__ == "__main__":
    main()