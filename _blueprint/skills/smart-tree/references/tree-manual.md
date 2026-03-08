# tree(1) — Full Manual Reference

> This is the complete `tree` man page, provided as a reference for the
> smart-tree skill. The skill's compact flag reference covers the essentials;
> consult this file when you need deep knowledge of a specific flag or behavior.
>
> Source: `man tree` (Tree v2.2.1)

---

## NAME

tree - list contents of directories in a tree-like format.

## SYNOPSIS

```
tree [-acdfghilnpqrstuvxACDFJQNSUX] [-L level [-R]] [-H [-]baseHREF]
     [-T title] [-o filename] [-P pattern] [-I pattern] [--gitignore]
     [--gitfile[=]file] [--matchdirs] [--metafirst] [--ignore-case]
     [--nolinks] [--hintro[=]file] [--houtro[=]file] [--inodes] [--device]
     [--sort[=]name] [--dirsfirst] [--filesfirst] [--filelimit[=]#] [--si]
     [--du] [--prune] [--charset[=]X] [--timefmt[=]format] [--fromfile]
     [--fromtabfile] [--fflinks] [--info] [--infofile[=]file] [--noreport]
     [--hyperlink] [--scheme[=]schema] [--authority[=]hostname] [--opt-toggle]
     [--version] [--help] [--] [directory ...]
```

## DESCRIPTION

Tree is a recursive directory listing program that produces a depth indented
listing of files, which is colorized ala dircolors if the LS_COLORS environment
variable is set and output is to tty. With no arguments, tree lists the files
in the current directory. When directory arguments are given, tree lists all the
files and/or directories found in the given directories each in turn. Upon
completion of listing all files/directories found, tree returns the total number
of files and/or directories listed.

By default, when a symbolic link is encountered, the path that the symbolic link
refers to is printed after the name of the link in the format:

    name -> real-path

If the `-l` option is given and the symbolic link refers to an actual directory,
then tree will follow the path of the symbolic link as if it were a real directory.

---

## LISTING OPTIONS

| Flag | Description |
|------|-------------|
| `-a` | All files are printed. By default tree does not print hidden files (those beginning with a dot `.`). In no event does tree print `.` (current directory) and `..` (previous directory). |
| `-d` | List directories only. |
| `-l` | Follows symbolic links if they point to directories, as if they were directories. Symbolic links that will result in recursion are avoided when detected. |
| `-f` | Prints the full path prefix for each file. |
| `-x` | Stay on the current file-system only. Ala `find -xdev`. |
| `-L level` | Max display depth of the directory tree. |
| `-R` | Recursively cross down the tree each level directories (see `-L` option), and at each level outputting to a file named `00Tree.html` (ala `-o`). |

### `-P pattern`

List only those files that match the wild-card pattern. You may have multiple
`-P` options. Note: you must use the `-a` option to also consider those files
beginning with a dot `.` for matching.

Valid wildcard operators:
- `*` — any zero or more characters
- `**` — any zero or more characters as well as null `/`s (i.e. `/**/` may match a single `/`)
- `?` — any single character
- `[...]` — any single character listed between brackets (optional `-` for character range, e.g. `[A-Z]`)
- `[^...]` — any single character NOT listed in brackets
- `|` — separates alternate patterns
- A `/` at the end of the pattern matches directories, but not files.

### `-I pattern`

Do not list those files that match the wild-card pattern. You may have multiple
`-I` options. See `-P` above for wildcard pattern syntax.

| Flag | Description |
|------|-------------|
| `--gitignore` | Uses git `.gitignore` files for filtering files and directories. Also uses `$GIT_DIR/info/exclude` if present. |
| `--gitfile[=]file` | Use file explicitly as a gitignore file. |
| `--ignore-case` | If a match pattern is specified by the `-P` or `-I` option, this will cause the pattern to match without regard to the case of each letter. |
| `--matchdirs` | If a match pattern is specified by the `-P` option, this will cause the pattern to be applied to directory names (in addition to filenames). In the event of a match on the directory name, matching is disabled for the directory's contents. If the `--prune` option is used, empty folders that match the pattern will not be pruned. |
| `--metafirst` | Print the meta-data information at the beginning of the line rather than after the indentation lines. |
| `--prune` | Makes tree prune empty directories from the output, useful when used in conjunction with `-P` or `-I`. See BUGS AND NOTES below. |
| `--info` | Prints file comments found in `.info` files. See .INFO FILES below. |
| `--infofile[=]file` | Use file explicitly as an info file. |
| `--noreport` | Omits printing of the file and directory report at the end of the tree listing. |
| `--charset[=]charset` | Set the character set to use when outputting HTML and for line drawing. |
| `--filelimit[=]#` | Do not descend directories that contain more than `#` entries. |
| `--timefmt[=]format` | Prints (implies `-D`) and formats the date according to the format string which uses the `strftime(3)` syntax. |
| `-o filename` | Send output to filename. |

---

## FILE OPTIONS

| Flag | Description |
|------|-------------|
| `-q` | Print non-printable characters in filenames as question marks instead of the default. |
| `-N` | Print non-printable characters as is instead of as escaped octal numbers. |
| `-Q` | Quote the names of files in double quotes. |
| `-p` | Print the file type and permissions for each file (as per `ls -l`). |
| `-u` | Print the username, or UID # if no username is available, of the file. |
| `-g` | Print the group name, or GID # if no group name is available, of the file. |
| `-s` | Print the size of each file in bytes along with the name. |
| `-h` | Print the size of each file in a more human readable way (K, M, G, T, P, E). |
| `--si` | Like `-h` but use SI units (powers of 1000) instead. |
| `--du` | For each directory report its size as the accumulation of sizes of all its files and sub-directories. The total amount of used space is also given in the final report (like `du -c`). This option requires tree to read the entire directory tree before emitting it. Implies `-s`. |
| `-D` | Print the date of the last modification time or if `-c` is used, the last status change time for the file listed. |
| `-F` | Append a `/` for directories, a `=` for socket files, a `*` for executable files, a `>` for doors (Solaris) and a `\|` for FIFOs, as per `ls -F`. |
| `--inodes` | Prints the inode number of the file or directory. |
| `--device` | Prints the device number to which the file or directory belongs. |

---

## SORTING OPTIONS

| Flag | Description |
|------|-------------|
| `-v` | Sort the output by version. |
| `-t` | Sort the output by last modification time instead of alphabetically. |
| `-c` | Sort the output by last status change instead of alphabetically. Modifies the `-D` option (if used) to print the last status change instead of modification time. |
| `-U` | Do not sort. Lists files in directory order. Disables `--dirsfirst`. |
| `-r` | Sort the output in reverse order. This is a meta-sort that alters the above sorts. Disabled when `-U` is used. |
| `--dirsfirst` | List directories before files. This is a meta-sort that alters the above sorts. Disabled when `-U` is used. |
| `--filesfirst` | List files before directories. This is a meta-sort that alters the above sorts. Disabled when `-U` is used. |
| `--sort[=]type` | Sort the output by type instead of name. Possible values: `ctime` (`-c`), `mtime` (`-t`), `size`, `version` (`-v`) or `none` (`-U`). |

---

## GRAPHICS OPTIONS

| Flag | Description |
|------|-------------|
| `-i` | Makes tree not print the indentation lines, useful when used in conjunction with the `-f` option. Also removes as much whitespace as possible when used with the `-J` or `-X` options. |
| `-A` | Turn on ANSI line graphics hack when printing the indentation lines. |
| `-S` | Turn on CP437 line graphics (useful when using Linux console mode fonts). Equivalent to `--charset=IBM437`. |
| `-n` | Turn colorization off always, over-ridden by the `-C` option. |
| `-C` | Turn colorization on always, using built-in color defaults if the `LS_COLORS` or `TREE_COLORS` environment variables are not set. Useful to colorize output to a pipe. |

---

## XML/JSON/HTML/HYPERLINKS OPTIONS

| Flag | Description |
|------|-------------|
| `-X` | Turn on XML output. |
| `-J` | Turn on JSON output. |
| `-H [-]baseHREF` | Turn on HTML output, including HTTP references. If baseHREF begins with a dash (`-`), the dash is removed and tree removes the first directory name from the href URL. |
| `--hintro[=]file` | Use file as the HTML intro in place of the default one. |
| `--houtro[=]file` | Use file as the HTML outro in place of the default one. |
| `-T title` | Sets the title and H1 header string in HTML output mode. |
| `--nolinks` | Turns off hyperlinks in HTML output. |
| `--hyperlink` | Enable OSC 8 terminal hyperlinks for terminals that support them. |
| `--scheme[=]schema` | Sets the schema used in the OSC 8 hyperlinks. Default: `file://`. |
| `--authority[=]hostname` | Sets the authority (hostname) to use for the OSC 8 hyperlinks. Default: local hostname. |

---

## INPUT OPTIONS

| Flag | Description |
|------|-------------|
| `--fromfile` | Reads a directory listing from a file rather than the file-system. Paths provided on the command line are files to read from rather than directories to search. The dot (`.`) indicates tree should read paths from standard input. |
| `--fromtabfile` | Like `--fromfile`, tree reads a directory tree from a text file where the files are tab indented in a tree like format. |
| `--fflinks` | Processes symbolic link information found in a file, as from the output of `tree -fi --noreport`. |

---

## MISC OPTIONS

| Flag | Description |
|------|-------------|
| `--opt-toggle` | Enables option "toggling". Turns on the ability to toggle options such as `-a`, `-h`, etc. Useful in aliases. |
| `--help` | Outputs a verbose usage listing. |
| `--version` | Outputs the version of tree. |
| `--` | Option processing terminator. No further options will be processed after this. |

---

## .INFO FILES

`.info` files are similar to `.gitignore` files. If a `.info` file is found while
scanning a directory it is read and added to a stack of `.info` information. Each
file is composed of comments (lines starting with hash marks `#`) or wild-card
patterns which may match a file relative to the directory the `.info` file is
found in. If a file should match a pattern, the tab indented comment that follows
the pattern is used as the file comment. A comment is terminated by a non-tab
indented line. Multiple patterns, each to a line, may share the same comment.

---

## FILES

| Path | Description |
|------|-------------|
| `/etc/DIR_COLORS` | System color database |
| `~/.dircolors` | User's color database |
| `.gitignore` | Git exclusion file |
| `$GIT_DIR/info/exclude` | Global git file exclusion list |
| `.info` | File comment file |
| `/usr/share/finfo/global_info` | Global file comment file |

---

## ENVIRONMENT

| Variable | Description |
|----------|-------------|
| `LS_COLORS` | Color information created by dircolors |
| `TREE_COLORS` | Uses this for color information over `LS_COLORS` if set |
| `TREE_CHARSET` | Character set for tree to use in HTML mode |
| `CLICOLOR` | Enables colorization even if `TREE_COLORS` or `LS_COLORS` is not set |
| `CLICOLOR_FORCE` | Always enables colorization (effectively `-C`) |
| `NO_COLOR` | Disable colorization (effectively `-n`). See https://no-color.org/ |
| `LC_CTYPE` | Locale for filename output |
| `LC_TIME` | Locale for timefmt output |
| `TZ` | Timezone for timefmt output |
| `STDDATA_FD` | Enable the stddata feature, optionally set descriptor to use |

---

## BUGS AND NOTES

- Tree does not prune "empty" directories when the `-P` and `-I` options are used by default. Use the `--prune` option.
- The `-h` and `--si` options round to the nearest whole number unlike the `ls` implementations which rounds up always.
- Pruning files and directories with the `-I`, `-P` and `--filelimit` options will lead to incorrect file/directory count reports.
- The `--prune` and `--du` options cause tree to accumulate the entire tree in memory before emitting it. For large directory trees this can cause a significant delay in output and the use of large amounts of memory.
- The timefmt expansion buffer is limited to 255 characters.
- XML/JSON trees are not colored.
- OSC 8 hyperlinks may be poorly supported by your terminal.

---

*Tree v2.2.1 — Author: Steve Baker (Steve.Baker.llc@gmail.com)*
