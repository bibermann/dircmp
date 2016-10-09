# dircmp

Directory comparison tool. Useful if you have to sync huge collections of files with different (altered) directory structures. The output is as minimal as possible.

Currently there are two search modes:
* dirs
* files

The output contains lists of:
* _left_ subjects with the respective partners from _right_. 
* _left_ subjects with no partners found.

## dirs mode

Tries to match _left_ directories in its entirety somewhere on the _right_.

## files mode

Tries to match each file from the _left_ somewhere on the _right_.
If entire directories match, they are listet instead of each containing file
to emphasize the directory match.

## helper scripts

dircmp_scan.py and dircmp_info.py provide sub functionality from dircmp.py for convenience.

## Licence

dircmp.py, dircmp_scan.py and dircmp_info.py are released under the Boost Software License.
