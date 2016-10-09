#!/usr/bin/env python

import dircmp_scan
import dircmp_info
import os
import time
import argparse
import json
import re
import enum
import sys
import cPickle as pickle
import hashlib

class TagValue(enum.Enum):
    none = 1
    allTrue = 2
    allFalse = 3
    conflict = 4

def hashFileId( fileId, ignoreModified ):
    if ignoreModified:
        return [hashlib.sha1( pickle.dumps( (fileId['isDir'], fileId['size']) ) ).hexdigest()]
    else:
        # +- 10 seconds
        timestampBy10 = int(fileId['modified']/100.0)
        return [
            hashlib.sha1( pickle.dumps( (fileId['isDir'], fileId['size'], timestampBy10-1) ) ).hexdigest(),
            hashlib.sha1( pickle.dumps( (fileId['isDir'], fileId['size'], timestampBy10+0) ) ).hexdigest(),
            hashlib.sha1( pickle.dumps( (fileId['isDir'], fileId['size'], timestampBy10+1) ) ).hexdigest()
            ]

def compareFiles( a, b, ignoreModified ):
    if a['isDir'] != b['isDir']: return False
    if a['size'] != b['size']: return False
    if not ignoreModified:
        if abs( a['modified'] - b['modified'] ) > 2*60: return False
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
        if time.time() - lastOutput > 10:
            print( '%i/%i...' % (counter, len(subjects)) )
            lastOutput = time.time()

    printPartnersSimple( subjects, partners, leftCommonRootLen, rightCommonRootLen, args )

def findFiles( leftDirectory, rightDirectory, leftIndex, rightIndex, leftCommonRootLen, rightCommonRootLen, exclude, include, args ):
    print( 'indexing targets...' )
    rightFileIdIndex = {}
    for rightPath in rightIndex:
        rightFileId = rightIndex[rightPath]
        targetHashes = hashFileId( rightFileId, args.ignore_modified )
        for targetHash in targetHashes:
            if not targetHash in rightFileIdIndex:
                rightFileIdIndex[targetHash] = []
            rightFileIdIndex[targetHash].append( rightFileId )

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
        subjectHashes = hashFileId( subject, args.ignore_modified )
        found = False
        for subjectHash in subjectHashes:
            if found: break
            if subjectHash in rightFileIdIndex:
                for potentialTarget in rightFileIdIndex[subjectHash]:
                    if found: break
                    if subject['path'] == potentialTarget['path']:
                        continue
                    if compareFiles( subject, potentialTarget, args.ignore_modified ):
                        partners.append( (subject, potentialTarget) )
                        found = True
                        break

        counter += 1
        if time.time() - lastOutput > 10:
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

def rewritePaths( directory, oldRootLen, newRoot ):
    for filename in directory:
        fileId = directory[filename]
        fileId['path'] = newRoot + fileId['path'][oldRootLen:]
        rewritePaths( fileId['children'], oldRootLen, newRoot )

def filterDirectory( include, exclude, directory ):
    newDirectory = {}
    for name in directory:
        fileId = directory[name]
        if not checkFilter( exclude, include, fileId['path'] ):
            continue
        newDirectory[name] = {}
        for key in fileId:
            if key == 'children':
                newDirectory[name][key] = filterDirectory( include, exclude, fileId[key] )
            else:
                newDirectory[name][key] = fileId[key]
    return newDirectory

def scan( rootGiven, rewriteRoot, name, saveAs, onlyScan, skipScan, include, exclude, args ):
    root = os.path.abspath( rootGiven.replace( '\\', '/' ) )
    if rewriteRoot:
        rootRewritten = os.path.abspath( rewriteRoot.replace( '\\', '/' ) )

    if os.path.isdir( root ):
        print( "scanning %s..." % name )
        directory = dircmp_scan.scanIntoMemory( root, onlyScan, skipScan )
        with open( saveAs, 'w' ) as outfile:
            json.dump( directory, outfile, indent = 4 )
    else:
        print( "loading %s..." % name )
        with open( root, 'r' ) as infile:
            directory = json.load( infile )

    if exclude or include:
        print( 'filtering data...' )
        directory = filterDirectory( include, exclude, directory )
        if not directory:
            print( "Error: root filtered out." )
            sys.exit( 1 )

    if rewriteRoot:
        firstEntry = directory[list(directory.keys())[0]]
        commonRootLen = len( firstEntry['path'] ) - len( firstEntry['name'] )

        rewritePaths( directory, commonRootLen-1, rootRewritten )

    firstEntry = directory[list(directory.keys())[0]]
    commonRootLen = len( firstEntry['path'] ) - len( firstEntry['name'] )

    index = dircmp_info.indexDirectory( directory )
    dircmp_info.printIndexResult( index )

    print( '%s root: %s' % (name, firstEntry['path'][:commonRootLen-1]) )

    return directory, index, commonRootLen

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument( 'mode', choices=['dirs','files'] )
    parser.add_argument( 'left', help = 'directory or json file' )
    parser.add_argument( 'right', help = 'directory or json file' )
    parser.add_argument( '--ignore-modified', action = 'store_true' )
    parser.add_argument( '--partners-only', action = 'store_true' )
    parser.add_argument( '--singles-only', action = 'store_true' )
    parser.add_argument( '--only', action = 'append', help = 'include paths (exact match); only affects directory scans' )
    parser.add_argument( '--skip', action = 'append', help = 'exclude paths (exact match); only affects directory scans' )
    parser.add_argument( '--save-left', default = 'subjects.json', help = 'default: %(default)s; only affects directory scans' )
    parser.add_argument( '--save-right', default = 'targets.json', help = 'default: %(default)s; only affects directory scans' )
    parser.add_argument( '--exclude', action = 'append', help = 'exclude paths (regex match)' )
    parser.add_argument( '--include', action = 'append', help = 'include paths only (regex match)' )
    parser.add_argument( '--rewrite-left', help = 'rewrite left root directory for comparison' )
    parser.add_argument( '--rewrite-right', help = 'rewrite right root directory for comparison' )
    args = parser.parse_args()

    if args.only:
        onlyScan = set( map( lambda x: os.path.abspath( x.replace( '\\', '/' ) ), args.only ) )
    else:
        onlyScan = set()

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
        args.left, args.rewrite_left, 'subjects', args.save_left, onlyScan, skipScan, include, exclude, args
        )

    (rightDirectory, rightIndex, rightCommonRootLen) = scan( 
        args.right, args.rewrite_right, 'targets', args.save_right, onlyScan, skipScan, include, exclude, args
        )

    if args.mode == 'dirs':
        findDirectories( leftDirectory, rightDirectory, leftIndex, rightIndex, leftCommonRootLen, rightCommonRootLen, exclude, include, args )
    elif args.mode == 'files':
        findFiles( leftDirectory, rightDirectory, leftIndex, rightIndex, leftCommonRootLen, rightCommonRootLen, exclude, include, args )

if __name__ == "__main__":
    main()