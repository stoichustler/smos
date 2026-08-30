// Copyright 2026 The Fuchsia Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

use std::ffi::{OsStr, OsString};
use std::fs::File;
use std::io::{self, Read, Write};

fn usage() -> i32 {
    eprintln!("Usage: cat [-u] [file ...]");
    1
}

fn copy<R: Read, W: Write>(reader: &mut R, writer: &mut W) -> io::Result<()> {
    let mut buffer = [0u8; 8192];
    let mut last_byte = None;

    loop {
        let count = reader.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        writer.write_all(&buffer[..count])?;
        last_byte = Some(buffer[count - 1]);
    }

    if last_byte != Some(b'\n') {
        writer.write_all(b"\n")?;
    }
    Ok(())
}

fn run<I>(args: I) -> i32
where
    I: IntoIterator<Item = OsString>,
{
    let mut files = Vec::new();
    let mut options = true;
    for arg in args {
        if options && arg == OsStr::new("--") {
            options = false;
        } else if options && arg == OsStr::new("-u") {
            // std::io::copy writes directly to the locked stdout stream, so
            // there is no additional userspace output buffer to disable.
        } else if options && arg.to_string_lossy().starts_with('-') {
            return usage();
        } else {
            options = false;
            files.push(arg);
        }
    }

    if files.is_empty() {
        return usage();
    }

    let stdin = io::stdin();
    let stdout = io::stdout();
    let mut input = stdin.lock();
    let mut output = stdout.lock();
    let mut status = 0;

    for path in files {
        if path == OsStr::new("-") {
            if let Err(error) = copy(&mut input, &mut output) {
                eprintln!("cat: <stdin>: {error}");
                status = 1;
            }
            continue;
        }

        match File::open(&path) {
            Ok(mut file) => {
                if let Err(error) = copy(&mut file, &mut output) {
                    eprintln!("cat: {}: {error}", path.to_string_lossy());
                    status = 1;
                }
            }
            Err(error) => {
                eprintln!("cat: {}: {error}", path.to_string_lossy());
                status = 1;
            }
        }
    }

    if let Err(error) = output.flush() {
        eprintln!("cat: <stdout>: {error}");
        status = 1;
    }
    status
}

fn main() {
    std::process::exit(run(std::env::args_os().skip(1)));
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;

    #[test]
    fn copies_bytes_without_text_conversion_and_adds_newline() {
        let mut input = Cursor::new(vec![0, 1, 2, 255]);
        let mut output = Vec::new();
        copy(&mut input, &mut output).unwrap();
        assert_eq!(output, vec![0, 1, 2, 255, b'\n']);
    }

    #[test]
    fn does_not_duplicate_existing_newline() {
        let mut input = Cursor::new(b"content\n".to_vec());
        let mut output = Vec::new();
        copy(&mut input, &mut output).unwrap();
        assert_eq!(output, b"content\n");
    }

    #[test]
    fn adds_newline_to_empty_input() {
        let mut input = Cursor::new(Vec::new());
        let mut output = Vec::new();
        copy(&mut input, &mut output).unwrap();
        assert_eq!(output, b"\n");
    }

    #[test]
    fn rejects_missing_file_operand_without_reading_stdin() {
        assert_eq!(run(Vec::<OsString>::new()), 1);
    }
}
