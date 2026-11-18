# Lesson checker (prototype)

The checker reads the C++ examples marked in the lesson Markdown files and in
directory projects, checks the markup and the Polish/English pairs, and then
compiles and runs the examples in the way each marker asks for.

**Status: prototype.** It is tested on technical fixtures in
`tests/checker/fixtures/`; the course has no lessons yet. The modes
`diagnostic`, `concurrent` and `benchmark` are reserved names and are not
implemented.

Requirements: Python 3.10+ (standard library only), LLVM Clang 22 or newer
used through the `clang++` driver, and, for directory projects, CMake 3.28+
and Ninja. Nothing is downloaded while checking.

## Commands

Run from the repository root:

| Command | What it does |
|---|---|
| `python -m tools.checker check PATH... [--cxx CLANG++] [--report FILE]` | Markup, paths, projects and PL/EN pairs, then builds and runs the examples. |
| `python -m tools.checker lint PATH...` | The same checks without a compiler: markup, paths, projects, PL/EN pairs. |
| `python -m tools.checker compare REPORT REPORT...` | Compares the stable fields of reports from different systems. |
| `python -m tools.checker selftest [-k TEXT] [--verbose]` | Runs the checker's own tests (`tests/checker/test_*.py`). |
| `python -m tools.checker toolchain [--cxx CLANG++]` | Prints the detected Clang, standard library, CMake and Ninja. |

`PATH` is a lesson file or a folder inside the repository; every `*.md` file
under a folder is a lesson. Other options of `check`: `--cmake`, `--ninja`,
`--min-clang` (default 22), `--work-dir`, `--keep-work`,
`--compile-timeout` (default 120 s), `--run-timeout` (default 10 s),
`--output-limit` (default 65,536 bytes per stream), `--verbose`.
`--cxx` defaults to `$CXX`, then `clang++`.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Every verdict passed. |
| 1 | A content failure: an example built or behaved differently from its marker. |
| 2 | A protocol error: markup, a path, a project manifest or a PL/EN pair (also a bad command line). |
| 3 | An environment problem: a missing or too old tool, a crashed compiler, a timeout of a tool. |
| 4 | An internal error of the checker, including a broken safety guarantee. |

With several kinds of problems, the highest code is returned and every problem is reported.

## Markers

A marker is an HTML comment on a line of its own, not indented, directly
above its code block; only blank lines may come in between. Parts are
separated by single spaces, and attributes appear only in the order shown.

| Marker | Block | Meaning |
|---|---|---|
| `<!-- run: NAME [exit=N] [source=PATH] [data=DIR] -->` | `cpp` | Build with the strict flags, run once per `output` block, compare stdout. |
| `<!-- input: NAME -->` | `text` | Standard input of the next run of NAME. |
| `<!-- output: NAME [in=FILE] -->` | `text` | Exact expected stdout of one run of NAME; `in=` gives that run's standard input from a file. |
| `<!-- compile: NAME [source=PATH] -->` | `cpp` | Build and link with the strict flags; never run. |
| `<!-- test: NAME [source=PATH] [data=DIR] [against=PATH] -->` | `cpp` | Build a check program and run it: exit code 0 and empty stderr pass; stdout is only logged. `against=` also requires it to reject a faulty implementation. |
| `<!-- compile_fail: NAME at=LINE[:COL] error=REGEX -->` | `cpp` | Must fail to compile with a real error at that place in `main.cpp`. |
| `<!-- compile_unsafe: NAME [allow=-WFLAG@LINE,...] -->` | `cpp` | Static check only (`-fsyntax-only`): never linked, never run. |
| `<!-- file: NAME PATH [source=PATH] -->` | `cpp` | Another file of program NAME (a flat `.cpp` or `.hpp` name), or a file shown from project NAME. |
| `<!-- project: NAME dir=PATH mode=compile\|run\|test [target=T] [exit=N] [data=DIR] -->` | none | A directory project; `mode=run` takes `output` blocks. |
| `<!-- fragment -->` | `cpp` | Deliberately incomplete code; never compiled. |

- **NAME** uses lowercase letters, digits and `_`, and is unique in its lesson.
- **Every `cpp` block needs a marker.** An indented `cpp` block is reported, because it would never be checked.
- **Lookalikes are errors:** a comment such as `<!--run: x-->` or `<!-- Output: x -->` is reported, and so is an unknown kind directly above a `cpp` block.
- **Ordinary comments** such as `<!-- TODO: ... -->` stay text.
- **Only run programs take `input`/`output` blocks.** Such a block for a `compile_unsafe`, `compile`, `test` or `compile_fail` program is refused (`mode_conflict`), so no marker can make unsafe code run.
- **Marked blocks are ASCII.**
- **A lesson with any protocol error is not built at all.**

## Compiler flags

Every compiler call adds
`-std=c++20 -fno-color-diagnostics -fno-caret-diagnostics -fdiagnostics-show-option -fmessage-length=0`.

| Mode | Warning flags | Notes |
|---|---|---|
| `run`, `compile`, `test`, projects | `-Wall -Wextra -Wpedantic -Werror` | Any warning fails the build. Projects get the flags through `CMAKE_CXX_FLAGS`. |
| `compile_fail` | `-Wall -Wextra -Wpedantic` | Never `-Werror`: a warning cannot pass as the expected error. |
| `compile_unsafe` | `-Wall -Wextra -Wpedantic` | Exactly the warnings listed in `allow=` must appear; any other warning fails. |

### `compile_fail`

The example passes only when all of these hold:

- the compiler ran and did not crash (otherwise: an environment problem);
- compilation failed;
- the first real error is in `main.cpp` at `at=`;
- its message matches `error=`.

An error tagged `[-Werror,...]` (a warning turned into an error by
`-Werror` or by `#pragma clang diagnostic error`) is not a real error. An
error with an ordinary option tag, such as narrowing
(`[-Wc++11-narrowing]`), is.

Clang is the compiler on every platform, but messages still differ between
the standard libraries (libc++, libstdc++, MSVC STL). Pin only a short,
stable part of the message after observing all three systems; the location
carries most of the check.

### `compile_unsafe`

For code that compiles but illustrates undefined or unsafe behaviour.

- The checker calls `clang++ -fsyntax-only` and refuses any argument list that could produce an output file.
- After the call it verifies that the example folder holds only the written sources.
- A pass means **"compiles with exactly the allowed warnings"**, nothing about whether the program is safe.

## Directory projects

`dir=` names a folder in the repository with a `CMakeLists.txt` and a
`checker-project.json` manifest:

```json
{"id": "spike_inventory", "modes": ["compile", "run", "test"],
 "targets": ["inventory_app", "inventory_checks"]}
```

- **Manifest rules:** a lesson may only use a mode and a target that the manifest declares; ids are unique across the checked lessons.
- **Build:** the project is copied to the work folder, configured with `cmake -G Ninja -DCMAKE_BUILD_TYPE=Debug` and the checked `clang++`, and built. Only the named target is built for `run` and `test`.
- **Refused contents:** `FetchContent`, `ExternalProject`, `execute_process`, custom commands and targets, `file(DOWNLOAD)` and `include(CTest)`.
- **Shown files:** a `file:` block with the project's NAME shows a project file; its PATH is relative to the project folder, and its content must equal that file.
- **Not a sandbox:** projects are reviewed material of this repository, not a safe place to run untrusted code.

## Standard input from a file (`in=`)

Each `output` block is one run, one control case. Its standard input
comes from exactly one place:

- the `input` block directly before it;
- the file named by `in=` on the `output` marker;
- or nothing (closed standard input).

An `input` block together with `in=` for the same run is a protocol error
(`input_conflict`).

```markdown
<!-- run: sum_numbers -->              (the program)
<!-- input: sum_numbers -->            case 1: inline data
<!-- output: sum_numbers -->
<!-- output: sum_numbers in=tests/checker/fixtures/data/stdin/numbers.txt -->   case 2: data from a file
```

The file is passed byte for byte. `in=` exists only on `output` markers,
which only `run` programs and projects with `mode=run` accept, so it cannot
start a `compile_unsafe` example.

## Data folders (`data=`)

`data=DIR` on a `run` or `test` program, or on a project with `mode=run`
or `mode=test`, names a folder in the repository.

- **Contract:** every run starts in a new, empty working folder that holds a copy of the folder's files. The program opens them by their names, for example `std::ifstream file{"readings.txt"}`.
- **What the program never sees:**
  - the original folder;
  - the repository;
  - the project's source or build folder.
- **Changes stay in the copy:** a program may change its copy; the next run gets a fresh one.
- **Originals are fingerprinted:** the checker takes SHA-256 fingerprints of the original data files and `in=` files before and after the runs. Any change is a failure (`source_modified`).
- **Byte for byte:** data files are not normalised. Keep Git from converting their line ends with a `.gitattributes` entry such as `data/** -text`, as `tests/checker/fixtures/.gitattributes` does. Every system then gets the same bytes, including files that are meant to have CRLF line ends.
- **Refused folders:** a data folder may not be a whole allowed root, may not contain symbolic links, and may hold at most 100 files and 4 MiB.
- **Only for programs that run:** `data=` is a protocol error on `compile`, `compile_fail` and `compile_unsafe`, and on projects with `mode=compile`.

## Checking that a test catches a fault (`against=`)

`against=PATH` on a `test` program names a deliberately faulty version of
one of the program's `file:` blocks, with the same file name. For example,
`against=.../negative_accepted/parse_count.cpp` replaces `parse_count.cpp`.

The faulty file must exist, must be ASCII, and must differ from the correct
file.

Besides the usual `NAME/build` and `NAME/test` verdicts, the program gets
one more verdict, `NAME/against`. It passes only when every step holds:

1. the check program builds and passes with the correct implementation;
2. it builds and links with the faulty file in place of the correct one;
3. it runs to the end;
4. it rejects the faulty implementation with the agreed report.

**The agreed report of failed checks** is:

- exit code 1;
- at least one stdout line that starts with `FAIL `;
- empty stderr.

| Category of a failed `NAME/against` | Meaning |
|---|---|
| `correct_failed` | the check program does not pass with the correct implementation |
| `faulty_build_failed` | the faulty file does not compile or link (not a detected fault) |
| `faulty_timeout`, `faulty_crashed`, `faulty_output_limit` | the check program hung, crashed or printed too much (not a detected fault) |
| `faulty_not_detected` | the check program passes with the faulty implementation too |
| `faulty_unrecognized` | it failed, but not with the agreed report (another exit code, no `FAIL ` line, or output on stderr) |

## Paths

Paths in markers (`source=`, `dir=`, `in=`, `data=`, `against=`) are relative to the repository root
and use `/`. Allowed roots are `course`, `projects`, `exercises`, `support`
and `tests/checker/fixtures`. The checker refuses:

- absolute paths and drive letters;
- `\` separators and any `..` segment;
- empty segments and segments starting with `.`;
- paths outside the allowed roots;
- missing files;
- symbolic links (and Windows junctions) anywhere in the path or inside a project.

Both files of a PL/EN pair may point to the same `source=` file or project.

## Polish and English pairs

- **Pairs:** every `X.md` has an `X.en.md` and the other way round.
- **Identical marked blocks:** both files have the same list of marker lines, in the same order, with identical code, input and output.
- **Normalisation:** `\r\n` is read as `\n` in lesson files, source files and program output. A lone `\r` is kept. No other normalisation is applied.
- **Built once:** the English file's examples are identical by this check, so only the Polish file's examples are built.
- **Prose** is not compared.

## Running examples

- **Process control:**
  - each tool and example starts in its own process group;
  - on a timeout or when a stream goes over the output limit, the whole group is stopped (`killpg` on POSIX, `taskkill /T /F` on Windows);
  - output is read while the program runs.
- **Work folders:**
  - every run starts in its own new folder inside the work folder, with a copy of the `data=` folder if one is declared;
  - the work folder is a new temporary folder by default; it may also be outside the repository or under `build/`, never elsewhere in the sources.
- **Environment:** started examples get a small environment (`PATH`, on Windows also `SYSTEMROOT`, `WINDIR`, `TEMP`, `TMP`) with `LC_ALL=C` and `TZ=UTC`, and closed or given standard input.
- **Commands:** commands are fixed argument lists (no shell); nothing written in the prose of a lesson is executed.
- **Logs:** reports show at most 1,000 characters of tool or program output per verdict.

These limits keep runs bounded and predictable. **They do not isolate the
examples from the system**: the checker is not a security sandbox.

## Reports

`--report FILE` writes sorted JSON with these parts:

- `environment`: platform, Clang version and target, standard library, CMake, Ninja, Python, and whether lesson files had Windows line ends;
- `summary`;
- `exit_code`;
- one record per verdict.

The stable fields of a verdict are `id`, `source`, `mode`, `expected`,
`status` and `category`. `compare` checks that they are identical between
reports. `actual`, `detail` and `duration_ms` differ between systems and are
not compared.

Verdict ids are `LESSON#NAME/build`, `/run1`, `/test`, `/against`, `/configure`, `/data` (only when an original data file changed), or
`LESSON#NAME` for `compile_fail` and `compile_unsafe`. Protocol errors use
`LESSON:LINE:CATEGORY`.

## Not implemented in this prototype

- `diagnostic`, `concurrent`, `benchmark` modes;
- `compile_fail` in a file other than `main.cpp`;
- link-stage failures;
- `against=` for directory projects;
- CTest-based project checks;
- comparison of the lesson structure (sections) between PL and EN;
- sharding.
