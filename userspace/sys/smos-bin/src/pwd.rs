use std::env;
use std::path::Path;

fn usage() -> ! {
    eprintln!("Usage: pwd [-LP]");
    std::process::exit(1);
}

fn main() {
    let mut mode = 'L';
    for arg in env::args_os().skip(1) {
        match arg.to_str() {
            Some("-L") => mode = 'L',
            Some("-P") => mode = 'P',
            Some("--") => break,
            _ => usage(),
        }
    }
    let cwd = match env::current_dir() {
        Ok(path) => path,
        Err(error) => {
            eprintln!("pwd: {error}");
            std::process::exit(1);
        }
    };
    if mode == 'L' {
        if let Some(pwd) = env::var_os("PWD") {
            let path = Path::new(&pwd);
            if path.is_absolute() && path.exists() {
                if let (Ok(a), Ok(b)) = (path.canonicalize(), cwd.canonicalize()) {
                    if a == b {
                        println!("{}", pwd.to_string_lossy());
                        return;
                    }
                }
            }
        }
    }
    println!("{}", cwd.display());
}
