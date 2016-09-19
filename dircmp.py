#!/usr/bin/env python

import os
import stat
import time
import argparse
import json
import re
import enum

class TagValue(enum.Enum):
    none = 1
    allTrue = 2
    allFalse = 3
    conflict = 4

def getFileId( root, filename ):
    path = os.path.join( root, filename )
    info = os.stat( path )
    return {
        'name' : filename,
        'path' : path,
        'isDir' : stat.S_ISDIR( info.st_mode ),
        'modified' : info.st_mtime,
        'size' : info.st_size
        }

def scanIntoMemory( root, skipScan ):
    progress = {}
    progress['lastOutput'] = time.time()
    progress['counter'] = 0
    return _scanIntoMemory( root, skipScan, progress )

def _scanIntoMemory( root, skipScan, progress ):
    directory = {}
    try:
        dirlist = os.listdir( root )
    except OSError:
        print( 'Could not access %s' % root )
        return directory
    for filename in os.listdir( root ):
        fileId = getFileId( root, filename )
        if fileId['path'] in skipScan:
            continue
        fileId['children'] = {}
        if fileId['isDir']:
            fileId['children'] = _scanIntoMemory( fileId['path'], skipScan, progress )
        directory[filename] = fileId

        progress['counter'] += 1
        if( time.time() - progress['lastOutput'] > 10 ):
            print( '%i...' % progress['counter'] )
            progress['lastOutput'] = time.time()

    return directory

def indexDirectory( directory ):
    index = {}
    for filename in directory:
        fileId = directory[filename]
        index[fileId['path']] = fileId
        index.update( indexDirectory( fileId['children'] ) )
    return index

def compareFiles( a, b, ignoreModified ):
    if a['isDir'] != b['isDir']: return False
    if a['size'] != b['size']: return False
    if not ignoreModified:
        if abs( a['modified'] - b['modified'] ) > 2: return False
    return True

def haveSameItems( list1, list2, id = lambda x: x ):
    set1 = set()
    set2 = set()
    for child in list1:
        item = list1[child]
        set1.add( id( item ) )
    for child in list2:
        item = list2[child]
        set2.add( id( item ) )
    return not (set1 ^ set2)

def compareDirectories( a, b, ignoreModified ):
    aChildren = a['children']
    bChildren = b['children']

    if not haveSameItems(
        aChildren,
        bChildren,
        lambda id: (id['isDir'], id['name'])
        ):
        return False

    for child in aChildren:
        aId = aChildren[child]
        bId = bChildren[child]
        if aId['isDir']:
            if not compareDirectories( aId, bId, ignoreModified ):
                return False
        else:
            if not compareFiles( aId, bId, ignoreModified ):
                return False

    return True

def findDirectories( leftDirectory, rightDirectory, leftIndex, rightIndex, leftCommonRootLen, rightCommonRootLen, exclude, include, args ):
    print( 'searching directory partners...' )
    lastOutput = time.time()

    subjects = []
    for leftFile in leftDirectory:
        leftFileId = leftDirectory[leftFile]
        if not checkFilter( exclude, include, leftFileId['path'] ):
            continue
        if leftFileId['isDir'] and leftFileId['children']:
            subjects.append( leftFileId )

    partners = []
    subjects = sorted( subjects, key = lambda s: s['name'].lower() )
    counter = 0
    for subject in subjects:
        for rightPath in rightIndex:
            if subject['path'] == rightPath:
                continue
            rightFileId = rightIndex[rightPath]
            if rightFileId['isDir']:
                if compareDirectories( subject, rightFileId, args.ignore_modified ):
                    partners.append( (subject, rightFileId) )
                    
        counter += 1
        if( time.time() - lastOutput > 10 ):
            print( '%i/%i...' % (counter, len(subjects)) )
            lastOutput = time.time()

    printPartnersSimple( subjects, partners, leftCommonRootLen, rightCommonRootLen, args )

def findFiles( leftDirectory, rightDirectory, leftIndex, rightIndex, leftCommonRootLen, rightCommonRootLen, exclude, include, args ):
    print( 'searching file partners...' )
    lastOutput = time.time()

    subjects = []
    for leftPath in leftIndex:
        leftFileId = leftIndex[leftPath]
        if not leftFileId['isDir']:
            subjects.append( leftFileId )

    partners = []
    subjects = sorted( subjects, key = lambda s: s['path'].lower() )
    counter = 0
    for subject in subjects:
        for rightPath in rightIndex:
            if subject['path'] == rightPath:
                continue
            rightFileId = rightIndex[rightPath]
            if compareFiles( subject, rightFileId, args.ignore_modified ):
                partners.append( (subject, rightFileId) )

        counter += 1
        if( time.time() - lastOutput > 10 ):
            print( '%i/%i...' % (counter, len(subjects)) )
            lastOutput = time.time()

    printPartnersGroup( subjects, partners, leftDirectory, rightDirectory, leftIndex, rightIndex, leftCommonRootLen, rightCommonRootLen, args )

def checkFilter( exclude, include, path ):
    if include and sum(1 for regex in include if regex.search( path )) == 0:
        return False
    if sum(1 for regex in exclude if regex.search( path )) > 0:
        return False
    return True

def printPartnersSimple( subjects, partners, leftCommonRootLen, rightCommonRootLen, args ):
    color_green = '\033[92m'
    color_red   = '\033[91m'
    color_blue = '\033[94m'
    color_end   = '\033[0m'

    print( '%i partners found.' % len( partners ) )
    if not args.singles_only:
        for partner in partners:
            print( '%s%s%s has partner %s%s%s' % (
                color_green, partner[0]['path'][leftCommonRootLen:], color_end,
                color_blue, partner[1]['path'][rightCommonRootLen:], color_end
                ) )

    if not args.partners_only:
        singles = []
        matchedSubjects = set( map( lambda x: x[0]['path'], partners ) )
        for subject in sorted( subjects, key = lambda s: s['name'].lower() ):
            if not subject['path'] in matchedSubjects:
                singles.append( subject )
        print( '%i singles (without partner).' % len( singles ) )
        for single in singles:
            print( '%s%s%s has no partner' % (
                color_red, single['path'][leftCommonRootLen:], color_end,
                ) )

def markDirectoriesContainingTaggedFiles( directory, tag, directoryFileId = None ):
    tagValue = TagValue.none
    for filename in directory:
        fileId = directory[filename]
        if fileId['isDir']:
            markDirectoriesContainingTaggedFiles( fileId['children'], tag, fileId )
        if tagValue == TagValue.none:
            tagValue = fileId[tag]
        elif tagValue != fileId[tag]:
            tagValue = TagValue.conflict
    if directoryFileId:
        directoryFileId[tag] = tagValue

def appendTaggedItems( itemList, directory, tag ):
    for filename in directory:
        fileId = directory[filename]
        if fileId[tag] == TagValue.allTrue:
            itemList.append( fileId )
        else:
            if fileId['isDir']:
                appendTaggedItems( itemList, fileId['children'], tag )

def printPartnersGroup( subjects, partners, leftDirectory, rightDirectory, leftIndex, rightIndex, leftCommonRootLen, rightCommonRootLen, args ):
    color_green = '\033[92m'
    color_red   = '\033[91m'
    color_blue = '\033[94m'
    color_end   = '\033[0m'

    # as in printPartnersSimple
    print( '%i partners found.' % len( partners ) )
    if not args.singles_only:
        for partner in partners:
            print( '%s%s%s has partner %s%s%s' % (
                color_green, partner[0]['path'][leftCommonRootLen:], color_end,
                color_blue, partner[1]['path'][rightCommonRootLen:], color_end
                ) )

    if not args.partners_only:
        singles = []
        matchedSubjects = set( map( lambda x: x[0]['path'], partners ) )
        for subject in sorted( subjects, key = lambda s: s['name'].lower() ):
            if not subject['path'] in matchedSubjects:
                singles.append( subject )
        print( '%i singles (without partner).' % len( singles ) )
        # mark files
        for leftPath in leftIndex:
            leftFileId = leftIndex[leftPath]
            leftFileId['single'] = TagValue.none if leftFileId['isDir'] else TagValue.allFalse
        for single in singles:
            leftIndex[single['path']]['single'] = TagValue.allTrue
        # mark directories
        markDirectoriesContainingTaggedFiles( leftDirectory, 'single' )
        singles = []
        appendTaggedItems( singles, leftDirectory, 'single' )
        for single in singles:
            print( '%s%s%s has no partner' % (
                color_red, single['path'][leftCommonRootLen:] + ('/' if single['isDir'] else ''), color_end,
                ) )

def printIndexResult( index ):
    print( '%i files (%f GiB) and %i folders (%i non-empty) found.' % (
        sum( not index[s]['isDir'] for s in index ),
        sum( index[s]['size'] for s in index )/1024.0/1024.0/1024.0,
        sum( index[s]['isDir'] for s in index ),
        sum( index[s]['isDir'] and bool( index[s]['children'] ) for s in index ),
        ) )

def rewritePaths( directory, oldRootLen, newRoot ):
    for filename in directory:
        fileId = directory[filename]
        fileId['path'] = newRoot + fileId['path'][oldRootLen:]
        rewritePaths( fileId['children'], oldRootLen, newRoot )

def scan( rootGiven, rewriteRoot, name, skipScan, exclude, include, args ):
    root = os.path.abspath( rootGiven.replace( '\\', '/' ) )
    if rewriteRoot:
        rootRewritten = os.path.abspath( rewriteRoot.replace( '\\', '/' ) )

    if os.path.isdir( root ):
        print( "scanning %s..." % name )
        directory = scanIntoMemory( root, skipScan )
        with open( args.save_left, 'w' ) as outfile:
            json.dump( directory, outfile, indent = 4 )
    else:
        print( "loading %s..." % name )
        with open( root, 'r' ) as infile:
            directory = json.load( infile )

    if rewriteRoot:
        firstEntry = directory[list(directory.keys())[0]]
        commonRootLen = len( firstEntry['path'] ) - len( firstEntry['name'] )

        rewritePaths( directory, commonRootLen-1, rootRewritten )

    firstEntry = directory[list(directory.keys())[0]]
    commonRootLen = len( firstEntry['path'] ) - len( firstEntry['name'] )

    index = indexDirectory( directory )
    printIndexResult( index )

    if exclude or include:
        print( 'filtering indices...' )
        filteredIndex = {}
        for path in index:
            if checkFilter( exclude, include, index[path]['path'] ):
                filteredIndex[path] = index[path]
    else:
        filteredIndex = index

    print( '%s root: %s' % (name, firstEntry['path'][:commonRootLen-1]) )

    return (directory, filteredIndex, commonRootLen)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument( 'mode', choices=['dirs','files'] )
    parser.add_argument( 'left', help = 'directory or json file' )
    parser.add_argument( 'right', help = 'directory or json file' )
    parser.add_argument( '--ignore-modified', action = 'store_true' )
    parser.add_argument( '--partners-only', action = 'store_true' )
    parser.add_argument( '--singles-only', action = 'store_true' )
    parser.add_argument( '--skip', action = 'append', help = 'exclude paths (exact match); only affects fresh scans' )
    parser.add_argument( '--save-left', default = 'subjects.json', help = 'only affects fresh scans' )
    parser.add_argument( '--save-right', default = 'targets.json', help = 'only affects fresh scans' )
    parser.add_argument( '--exclude', action = 'append', help = 'exclude paths (regex match)' )
    parser.add_argument( '--include', action = 'append', help = 'include paths only (regex match)' )
    parser.add_argument( '--rewrite-left', help = 'rewrite left root directory' )
    parser.add_argument( '--rewrite-right', help = 'rewrite right root directory' )
    args = parser.parse_args()

    if args.skip:
        skipScan = set( map( lambda x: os.path.abspath( x.replace( '\\', '/' ) ), args.skip ) )
    else:
        skipScan = set()

    if args.exclude:
        exclude = map( lambda pattern: re.compile( pattern ), args.exclude )
    else:
        exclude = []

    if args.include:
        include = map( lambda pattern: re.compile( pattern ), args.include )
    else:
        include = []

    (leftDirectory, leftIndex, leftCommonRootLen) = scan( 
        args.left, args.rewrite_left, 'subjects', skipScan, exclude, include, args
        )

    (rightDirectory, rightIndex, rightCommonRootLen) = scan( 
        args.right, args.rewrite_right, 'targets', skipScan, exclude, include, args
        )

    if args.mode == 'dirs':
        findDirectories( leftDirectory, rightDirectory, leftIndex, rightIndex, leftCommonRootLen, rightCommonRootLen, exclude, include, args )
    elif args.mode == 'files':
        findFiles( leftDirectory, rightDirectory, leftIndex, rightIndex, leftCommonRootLen, rightCommonRootLen, exclude, include, args )

if __name__ == "__main__":
    main()