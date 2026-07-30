mod client;
mod hwid;
mod token;

use clap::{Parser, Subcommand};
use std::fs;
use std::path::PathBuf;

const TOKEN_CACHE_FILE: &str = ".license_token";

#[derive(Parser)]
#[command(
    name = "pharmacy-hwid",
    about = "PharmacyPro — Secure hardware fingerprinting & offline license validation",
    version
)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Generate this machine's hardware ID (HWID)
    GenHwid,

    /// Validate a license key against the live server
    Validate {
        /// License key (e.g. PHARM-XXXX-XXXX-XXXX)
        #[arg(short, long)]
        key: String,

        /// HWID override (defaults to this machine)
        #[arg(long)]
        hwid: Option<String>,

        /// Server API base URL override
        #[arg(long)]
        server: Option<String>,
    },

    /// Activate a license key on this device
    Activate {
        /// License key
        #[arg(short, long)]
        key: String,

        /// HWID override (defaults to this machine)
        #[arg(long)]
        hwid: Option<String>,

        /// Server API base URL override
        #[arg(long)]
        server: Option<String>,
    },

    /// Verify an offline token locally (no server needed)
    VerifyToken {
        /// Offline token string (from a previous validate/activate response)
        #[arg(short, long)]
        token: Option<String>,

        /// Read token from cached file instead
        #[arg(long)]
        cached: bool,
    },

    /// Save an offline token to local cache
    SaveToken {
        /// Token string to cache
        #[arg(short, long)]
        token: String,
    },

    /// Check server health
    Health {
        /// Server API base URL override
        #[arg(long)]
        server: Option<String>,
    },
}

fn cache_path() -> PathBuf {
    let mut p = dirs::home_dir().unwrap_or_else(|| PathBuf::from("."));
    p.push(TOKEN_CACHE_FILE);
    p
}

#[tokio::main]
async fn main() {
    let cli = Cli::parse();

    match cli.command {
        Commands::GenHwid => {
            let hwid = hwid::generate_hwid();
            println!("HWID: {}", hwid);
        }

        Commands::Validate { key, hwid, server } => {
            let machine_hwid = hwid.unwrap_or_else(|| hwid::generate_hwid());
            let device_id = hwid::generate_hwid(); // simplified

            println!("Key  : {}", key);
            println!("HWID : {}", machine_hwid);
            println!("Server: {}", server.as_deref().unwrap_or("default"));
            println!();

            match client::validate(server.as_deref(), &key, &device_id, &machine_hwid).await {
                Ok(resp) => {
                    println!("Status : {}", if resp.valid { "VALID" } else { "INVALID" });
                    println!("Message: {}", resp.message);
                    if let Some(ref tok) = resp.offline_token {
                        println!("Offline token: {}...", &tok[..40.min(tok.len())]);
                        println!("Grace period : {} days", resp.offline_grace_days.unwrap_or(0));
                        // Auto-cache the token
                        let _ = fs::write(cache_path(), tok);
                        println!("Token cached to: {:?}", cache_path());
                    }
                }
                Err(e) => {
                    eprintln!("ERROR: {}", e);
                    std::process::exit(1);
                }
            }
        }

        Commands::Activate { key, hwid, server } => {
            let machine_hwid = hwid.unwrap_or_else(|| hwid::generate_hwid());
            let device_id = hwid::generate_hwid();

            println!("Key  : {}", key);
            println!("HWID : {}", machine_hwid);
            println!();

            match client::activate(server.as_deref(), &key, &device_id, &machine_hwid).await {
                Ok(resp) => {
                    println!("Status : {}", if resp.activated { "ACTIVATED" } else { "FAILED" });
                    println!("Message: {}", resp.message);
                    if let Some(ref tok) = resp.offline_token {
                        println!("Offline token: {}...", &tok[..40.min(tok.len())]);
                        let _ = fs::write(cache_path(), tok);
                        println!("Token cached to: {:?}", cache_path());
                    }
                }
                Err(e) => {
                    eprintln!("ERROR: {}", e);
                    std::process::exit(1);
                }
            }
        }

        Commands::VerifyToken { token, cached } => {
            let tok = if cached {
                match fs::read_to_string(cache_path()) {
                    Ok(t) => t.trim().to_string(),
                    Err(_) => {
                        eprintln!("No cached token at {:?}", cache_path());
                        std::process::exit(1);
                    }
                }
            } else {
                match token {
                    Some(t) => t,
                    None => {
                        eprintln!("Provide --token <TOKEN> or use --cached");
                        std::process::exit(1);
                    }
                }
            };

            println!("Verifying offline token (local)...");
            println!();

            let result = token::verify_token_offline(&tok);
            println!("Valid   : {}", result.valid);
            println!("Message : {}", result.message);
            if let Some(ref payload) = result.payload {
                println!("Key     : {}", payload.license_key);
                println!("HWID    : {}", payload.hwid);
                println!("Expires : {}", payload.expires_at);
                println!("Issued  : {}", payload.issued_at);
            }
        }

        Commands::SaveToken { token } => {
            let path = cache_path();
            fs::write(&path, token.trim()).expect("Failed to write token cache");
            println!("Token saved to: {:?}", path);
        }

        Commands::Health { server } => {
            match client::health(server.as_deref()).await {
                Ok(resp) => println!("Server status: {}", resp.status),
                Err(e) => {
                    eprintln!("ERROR: {}", e);
                    std::process::exit(1);
                }
            }
        }
    }
}
