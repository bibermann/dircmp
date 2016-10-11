# dircmp

Directory comparison tool. Useful if you have to sync huge collections of files with different (altered) directory structures. The output is as minimal as possible.

The output contains lists of:
* _left_ subjects with the respective partners from _right_. 
* _left_ subjects with no partners found.

Some features:
* Can compare the content of the files (uses hashes).
* Filtering with regular expressions.
* An index of the directory tree as well as generated hashes can be saved for offline usage.

## files mode (default)

Tries to match each file from the _left_ somewhere on the _right_.
If entire directories match, they are listet instead of each containing file to emphasize the directory match.

## dirs mode (--dirs)

Tries to match _left_ directories in its entirety somewhere on the _right_.

# dirscan

Directory scanning tool. Useful to search the directory tree (or a stored index).

Some features:
* Search for a regular expression, emphasizes matched groups.
* Filtering with regular expressions.
* Can hash files in advance for usage with `dircmp`.

## Licence

dircmp, dirscan and libdircmp.py are released under the Boost Software License.
