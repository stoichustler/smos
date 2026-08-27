// Copyright 2026 The Fuchsia Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

use std::ffi::{OsStr, OsString};
use std::io::Write;
use std::os::unix::ffi::{OsStrExt, OsStringExt};
use std::path::PathBuf;
use std::process::Command;

const DEFAULT_PATH: &str = "/boot/bin:/bin:/usr/bin";

fn usage() -> ! {
    eprintln!("Usage: env [-i] [-u var] ... [var=value] ... [cmd [arg ...]]");
    std::process::exit(1);
}

fn is_assignment(value: &OsStr) -> bool {
    value.as_bytes().contains(&b'=')
}

fn set_assignment(value: &OsStr) -> Result<(), ()> {
    let bytes = value.as_bytes();
    let separator = bytes.iter().position(|byte| *byte == b'=').ok_or(())?;
    let key = OsStr::from_bytes(&bytes[..separator]);
    if key.is_empty() {
        return Err(());
    }
    let value = OsStr::from_bytes(&bytes[separator + 1..]);
    std::env::set_var(key, value);
    Ok(())
}

fn command_for(program: &OsStr) -> Command {
    if program.as_bytes().contains(&b'/') {
        return Command::new(program);
    }

    let path = std::env::var_os("PATH").unwrap_or_else(|| OsString::from(DEFAULT_PATH));
    for directory in std::env::split_paths(&path) {
        let candidate: PathBuf = directory.join(program);
        if candidate.is_file() {
            return Command::new(candidate);
        }
    }

    Command::new(program)
}

fn run<I>(args: I) -> i32
where
    I: IntoIterator<Item = OsString>,
{
    let args: Vec<OsString> = args.into_iter().collect();
    let mut index = 0;
    let mut parse_options = true;

    while index < args.len() && parse_options {
        match args[index].as_os_str().as_bytes() {
            b"-i" => {
                // Clearing the inherited environment also makes assignments
                // that follow -i behave like the POSIX env utility.
                for (key, _) in std::env::vars_os().collect::<Vec<_>>() {
                    std::env::remove_var(key);
                }
                index += 1;
            }
            b"-u" => {
                index += 1;
                if index == args.len() {
                    usage();
                }
                std::env::remove_var(&args[index]);
                index += 1;
            }
            b"--" => {
                parse_options = false;
                index += 1;
            }
            value if value.starts_with(b"-") => usage(),
            _ => break,
        }
    }

    while index < args.len() && is_assignment(&args[index]) {
        if set_assignment(&args[index]).is_err() {
            eprintln!("env: invalid assignment: {}", args[index].to_string_lossy());
            return 1;
        }
        index += 1;
    }

    if index == args.len() {
        let mut status = 0;
        for (key, value) in std::env::vars_os() {
            let mut line = OsString::from(key);
            line.push("=");
            line.push(value);
            let bytes = line.into_vec();
            if let Err(error) = std::io::stdout().write_all(&bytes) {
                eprintln!("env: <stdout>: {error}");
                status = 1;
                break;
            }
            if let Err(error) = std::io::stdout().write_all(b"\n") {
                eprintln!("env: <stdout>: {error}");
                status = 1;
                break;
            }
        }
        return status;
    }

    match command_for(&args[index]).args(&args[index + 1..]).status() {
        Ok(status) => status.code().unwrap_or(1),
        Err(error) => {
            eprintln!("env: {}: {error}", args[index].to_string_lossy());
            if error.kind() == std::io::ErrorKind::NotFound {
                127
            } else {
                126
            }
        }
    }
}

fn main() {
    std::process::exit(run(std::env::args_os().skip(1)));
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn recognizes_assignments() {
        assert!(is_assignment(OsStr::new("A=B")));
        assert!(!is_assignment(OsStr::new("command")));
    }

    #[test]
    fn rejects_empty_assignment_names() {
        assert!(set_assignment(OsStr::new("=value")).is_err());
    }
}
