import os
import stat
import time
import json
import sys
import re

def calculateDirectorySizes( directory ):
    size = 0
    for name in directory:
        fileId = directory[name]
        if fileId['isDir']:
            fileId['size'] = calculateDirectorySizes( fileId['children'] )
        size += fileId['size']
    return size

def filterDirectory( include, exclude, directory ):
    newDirectory = {}
    for name in directory:
        fileId = directory[name]
        if not checkExcludeFilter( exclude, fileId['path'] ):
            continue
        includeThis = checkIncludeFilter( include, fileId['path'] )
        children = filterDirectory( include, exclude, fileId['children'] )
        if not includeThis and not children:
            continue
        newDirectory[name] = {}
        for key in fileId:
            if key == 'children':
                newDirectory[name][key] = children
            else:
                newDirectory[name][key] = fileId[key]
    return newDirectory

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

def formatMemory( bytes ):
    units = [ 'Byte', 'KiB', 'MiB', 'GiB', 'TiB' ]
    iUnit = 0
    memory = bytes
    while memory >= 1024.0 and iUnit + 1 < len( units ):
        memory /= 1024.0
        iUnit += 1
    return ('%.0f %s' if iUnit == 0 else '%.2f %s') % (memory, units[iUnit])

def checkIncludeFilter( include, path ):
    if include and sum(1 for regex in include if regex.search( path )) == 0:
        return False
    return True

def checkExcludeFilter( exclude, path ):
    if sum(1 for regex in exclude if regex.search( path )) > 0:
        return False
    return True

def rewritePaths( directory, oldRootLen, newRoot ):
    for filename in directory:
        fileId = directory[filename]
        fileId['path'] = newRoot + fileId['path'][oldRootLen:]
        rewritePaths( fileId['children'], oldRootLen, newRoot )

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

def scan( rootGiven, rewriteRoot, name, saveAs, args ):
    root = os.path.abspath( rootGiven.replace( '\\', '/' ) )

    if not os.path.isdir( root ):
        if args.only or args.skip:
            print( "Error: --only and --skip works only on directory scans." )
            sys.exit( 1 )
        if saveAs:
            print( "Error: scan results can only be saved of directory scans." )
            sys.exit( 1 )

    if rewriteRoot:
        rootRewritten = os.path.abspath( rewriteRoot.replace( '\\', '/' ) )

    if os.path.isdir( root ):
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

        print( "scanning %s..." % (name if name else root) )
        directory = scanIntoMemory( root, onlyScan, skipScan )
        with open( saveAs, 'w' ) as outfile:
            json.dump( directory, outfile, indent = 4 )
    elif os.path.isfile( root ):
        print( "loading %s..." % (name if name else root) )
        with open( root, 'r' ) as infile:
            directory = json.load( infile )
    else:
        print( "Error: %s does not exist." % root )
        sys.exit( 1 )

    if args.exclude or args.include:
        if args.exclude:
            exclude = map( lambda pattern: re.compile( pattern ), args.exclude )
        else:
            exclude = []

        if args.include:
            include = map( lambda pattern: re.compile( pattern ), args.include )
        else:
            include = []

        print( 'filtering data...' )
        directory = filterDirectory( include, exclude, directory )
        if not directory:
            print( "Error: root filtered out." )
            sys.exit( 1 )

    print( 'calculating directory sizes...' )
    calculateDirectorySizes( directory )

    if rewriteRoot:
        firstEntry = directory[list(directory.keys())[0]]
        commonRootLen = len( firstEntry['path'] ) - len( firstEntry['name'] )

        rewritePaths( directory, commonRootLen-1, rootRewritten )

    firstEntry = directory[list(directory.keys())[0]]
    commonRootLen = len( firstEntry['path'] ) - len( firstEntry['name'] )

    index = indexDirectory( directory )
    printIndexResult( index )

    if name:
        print( '%s root: %s' % (name, firstEntry['path'][:commonRootLen-1]) )
    else:
        print( 'root: %s' % firstEntry['path'][:commonRootLen-1] )

    return directory, index, commonRootLen