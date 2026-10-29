# serial-claim-audit

Version 0.1.0. Python >=3.9. MIT licensed. No runtime dependencies.

An offline static checker comparing documented wired port claims with Python
AST evidence. Audited code is never executed; no hardware or provider package
is needed.

```sh
python3 -m pip install .
serial-claim-audit ./project --json
python3 -m serial_claim_audit ./project --verbose
python3 -m unittest discover
python3 -m build
```

Root README.md and Markdown beneath any docs path component supply claims.
Fenced blocks are excluded; inline code counts. Matching lowercases text,
expands contractions ending in n't, converts hyphens to spaces, and joins
whitespace within blank-line-separated paragraphs. Word boundaries and exact
phrases apply, longest first; negative spans are removed before positive checks.

## Phrase vocabulary

Only the following templates count:

```text
connects to serial devices
connect to serial devices
connects over serial
connect over serial
communicates over serial
communicate over serial
communicates via serial
communicate via serial
reads from serial port
read from serial port
writes to serial port
write to serial port
reads data from serial port
read data from serial port
writes data to serial port
write data to serial port
sends data over serial
send data over serial
receives data over serial
receive data over serial
opens serial ports
open serial ports
serial port support
serial device support
serial connectivity
supports serial ports
support serial ports
supports serial
support serial
uses serial port
use serial port
uses serial
use serial
does not connect to serial devices
does not connect over serial
does not communicate over serial
does not communicate via serial
does not read from serial port
does not write to serial port
does not send data over serial
does not receive data over serial
does not support serial ports
does not support serial
does not use serial port
does not use serial
serial port not supported
serial not supported
no serial port support
without serial port support
no serial support
without serial support
no serial connectivity
without serial connectivity
no serial
without serial
```

Production evidence consists of provider-resolved pyserial constructors or
factories, asynchronous provider connection calls, and transfers on their
results. Imports and aliases are resolved per module; local class/function
names shadow imported names. Bare imports, strings, ordinary file opens,
unbound transfers, USB handles, printer objects, logging functions, decorators,
comments and docstrings do not establish evidence.

## Rules and CLI

`documented-serial-claim-false` reports HIGH when a positive template lacks
production evidence, or MEDIUM when evidence exists only in test source.
The negative rule below reports HIGH when a negative template
contradicts production evidence.

```text
documented-no-serial-claim-false
```

At most one finding per family is emitted.
Absent claims always pass. With no source, a positive template fails and a
negative template passes.

The positional root defaults to the current directory. `--json` emits valid
JSON containing verdict and findings with rule, severity, and message.
`--verbose` adds scan counts to human output. Repeat `--ignore GLOB` to exclude
relative paths. `--fail-on HIGH` is the default; MEDIUM findings are reported
without failure. `--fail-on MEDIUM` also fails on MEDIUM. Exit status is 0 for
PASS, 2 for FAIL, and 1 for an invalid or unreadable root. `--version` prints
0.1.0. Both entry points accept the same options.

## Limitations

Only the exact templates listed in the fenced block are recognized. A bare
protocol word, user cable setup instructions, USB reach, printing, Bluetooth
links, and file exports are outside this vocabulary. System terminal helpers
invoked through subprocesses are outside the evidence model: shell command
names in string literals never count.

This is syntax analysis, not runtime verification. Calls may be unreachable,
ports may be invalid, and control flow, dynamic imports, rebinding, and imported
wrappers are not evaluated. Syntax-invalid modules provide no evidence.
Source under tests, test-prefixed files and test-suffixed files is test scope;
fixtures, docs, and examples are excluded from evidence. Symlinked files and
directories are skipped. Environment files are never opened. No network or
hardware inspection occurs.
