# Rust guest manager

This directory contains the Rust implementation and unit tests for the
virtualization guest manager.

The SMOS migration currently builds the manager binary and its test package.
The Debian guest image package and the runtime component assembly are not part
of this compact tree. The CML files are retained as reference material and are
not included in the `packages` target.
