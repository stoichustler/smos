use std::fs;
use std::path::{Path, PathBuf};

#[derive(Clone)]
enum Pred {
    Name(String),
    Path(String),
    Type(char),
    Print,
    Prune,
    Xdev,
    True,
}
fn usage() -> ! {
    eprintln!("Usage: find [path ...] [expression]");
    std::process::exit(1);
}
fn wildcard(pattern: &str, text: &str) -> bool {
    fn go(p: &[u8], t: &[u8]) -> bool {
        if p.is_empty() {
            return t.is_empty();
        }
        match p[0] {
            b'*' => go(&p[1..], t) || (!t.is_empty() && go(p, &t[1..])),
            b'?' => !t.is_empty() && go(&p[1..], &t[1..]),
            c => !t.is_empty() && c == t[0] && go(&p[1..], &t[1..]),
        }
    }
    go(pattern.as_bytes(), text.as_bytes())
}
fn eval(preds: &[Pred], path: &Path, is_dir: bool) -> (bool, bool) {
    let mut result = true;
    let mut prune = false;
    let name = path.file_name().and_then(|x| x.to_str()).unwrap_or("");
    let text = path.to_string_lossy();
    for p in preds {
        match p {
            Pred::Name(x) => result &= wildcard(x, name),
            Pred::Path(x) => result &= wildcard(x, &text),
            Pred::Type(c) => result &= (*c == 'd' && is_dir) || (*c == 'f' && !is_dir),
            Pred::Print => {
                if result {
                    println!("{}", text);
                }
            }
            Pred::Prune => {
                if result {
                    prune = true;
                }
            }
            Pred::Xdev | Pred::True => {}
        }
    }
    (result, prune)
}
fn walk(path: PathBuf, preds: &[Pred], depth: bool, maxdepth: Option<usize>, level: usize) -> bool {
    let meta = match fs::symlink_metadata(&path) {
        Ok(m) => m,
        Err(e) => {
            eprintln!("find: {}: {e}", path.display());
            return true;
        }
    };
    let dir = meta.is_dir();
    if !depth {
        let (matched, prune) = eval(preds, &path, dir);
        if !preds.iter().any(|p| matches!(p, Pred::Print)) && matched {
            println!("{}", path.display());
        }
        if prune {
            return false;
        }
    }
    let mut had_error = false;
    if dir && maxdepth.map_or(true, |d| level < d) {
        match fs::read_dir(&path) {
            Ok(entries) => {
                for entry in entries {
                    match entry {
                        Ok(entry) => {
                            had_error |= walk(entry.path(), preds, depth, maxdepth, level + 1);
                        }
                        Err(e) => {
                            eprintln!("find: {}: {e}", path.display());
                            had_error = true;
                        }
                    }
                }
            }
            Err(e) => {
                eprintln!("find: {}: {e}", path.display());
                had_error = true;
            }
        }
    }
    if depth {
        let (matched, _) = eval(preds, &path, dir);
        if !preds.iter().any(|p| matches!(p, Pred::Print)) && matched {
            println!("{}", path.display());
        }
    }
    had_error
}
fn main() {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    let mut paths = Vec::new();
    let mut i = 0;
    while i < args.len() && !args[i].to_string_lossy().starts_with('-') {
        paths.push(PathBuf::from(&args[i]));
        i += 1;
    }
    if paths.is_empty() {
        paths.push(PathBuf::from("."));
    }
    let mut preds = Vec::new();
    let mut depth = false;
    let mut maxdepth = None;
    while i < args.len() {
        match args[i].to_str() {
            Some("-name") => {
                i += 1;
                preds.push(Pred::Name(
                    args.get(i).and_then(|x| x.to_str()).unwrap_or_else(|| usage()).into(),
                ));
            }
            Some("-path") => {
                i += 1;
                preds.push(Pred::Path(
                    args.get(i).and_then(|x| x.to_str()).unwrap_or_else(|| usage()).into(),
                ));
            }
            Some("-type") => {
                i += 1;
                preds.push(Pred::Type(
                    args.get(i)
                        .and_then(|x| x.to_str())
                        .and_then(|x| x.chars().next())
                        .unwrap_or_else(|| usage()),
                ));
            }
            Some("-print") => preds.push(Pred::Print),
            Some("-prune") => preds.push(Pred::Prune),
            Some("-xdev") => preds.push(Pred::Xdev),
            Some("-depth") => depth = true,
            Some("-maxdepth") => {
                i += 1;
                maxdepth = Some(
                    args.get(i)
                        .and_then(|x| x.to_str())
                        .and_then(|x| x.parse().ok())
                        .unwrap_or_else(|| usage()),
                );
            }
            Some("-a") | Some("-and") | Some("(") | Some(")") => {}
            Some("-true") => preds.push(Pred::True),
            Some(s) if s.starts_with('-') => usage(),
            _ => usage(),
        }
        i += 1;
    }
    if preds.is_empty() {
        preds.push(Pred::Print);
    }
    let mut status = walk(paths[0].clone(), &preds, depth, maxdepth, 0);
    for path in paths.into_iter().skip(1) {
        status |= walk(path, &preds, depth, maxdepth, 0);
    }
    if status {
        std::process::exit(1);
    }
}
