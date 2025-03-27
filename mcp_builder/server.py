#!/usr/bin/env python

import json
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Union

from mcp.server.fastmcp import Context, FastMCP

# Create MCP server
mcp = FastMCP(
    name="mcp-builder",
    version="0.1.0",
    description="A Python MCP server to install other MCP servers",
)

def get_claude_desktop_config_path() -> Optional[str]:
    """Get the path to the Claude Desktop configuration file."""
    home = os.path.expanduser("~")
    
    if platform.system() == "Windows":
        return os.path.join(os.environ.get("APPDATA", ""), "Claude", "claude_desktop_config.json")
    elif platform.system() == "Darwin":  # macOS
        return os.path.join(home, "Library", "Application Support", "Claude", "claude_desktop_config.json")
    else:  # Linux and others
        return os.path.join(home, ".config", "Claude", "claude_desktop_config.json")

def read_config() -> Dict:
    """Read the Claude Desktop configuration file."""
    config_path = get_claude_desktop_config_path()
    if not config_path or not os.path.exists(config_path):
        return {}
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

def write_config(config: Dict) -> None:
    """Write to the Claude Desktop configuration file."""
    config_path = get_claude_desktop_config_path()
    if not config_path:
        raise ValueError("Could not find Claude Desktop config file")
        
    config_dir = os.path.dirname(config_path)
    os.makedirs(config_dir, exist_ok=True)
    
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

def parse_env_vars(env_vars: Optional[List[str]]) -> Optional[Dict[str, str]]:
    """Parse environment variables from a list of KEY=VALUE strings."""
    if not env_vars:
        return None
        
    env_obj = {}
    for env_var in env_vars:
        if "=" in env_var:
            key, value = env_var.split("=", 1)
            env_obj[key] = value
            
    return env_obj if env_obj else None

def check_command_exists(command: str) -> bool:
    """Check if a command exists in the system PATH."""
    return shutil.which(command) is not None

def run_command(
    command: List[str], 
    cwd: Optional[Path] = None, 
    env: Optional[Dict[str, str]] = None
) -> tuple[bool, str]:
    """Run a command and return its success status and output."""
    try:
        env_dict = os.environ.copy()
        if env:
            env_dict.update(env)
        
        result = subprocess.run(
            command,
            cwd=cwd,
            env=env_dict,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0, result.stdout + result.stderr
    except Exception as e:
        return False, str(e)

def is_pypi_package(package_name: str) -> bool:
    """Check if a package exists on PyPI."""
    success, _ = run_command(["pip", "search", package_name])
    return success

def is_npm_package(package_name: str) -> bool:
    """Check if a package exists on npm."""
    success, _ = run_command(["npm", "view", package_name])
    return success

def install_to_claude_desktop(
    server_name: str,
    command: str,
    args: List[str],
    env: Optional[List[str]] = None,
    cwd: Optional[str] = None,
) -> None:
    """
    Install an MCP server to Claude Desktop.
    
    Args:
        server_name: The name of the MCP server
        command: The command to run the MCP server
        args: The arguments to pass to the command
        env: The environment variables to set, delimited by =
        cwd: The working directory for the command
    """
    # Normalize server name to be a valid identifier
    # For npm packages, make sure we use a simple name without @ or /
    if server_name.startswith("@"):
        # For @scope/package, use just "package" as the server name
        if "/" in server_name:
            server_name = server_name.split("/")[1]
    
    # Remove any invalid characters from server name
    server_name = re.sub(r'[^a-zA-Z0-9_-]', '-', server_name)
    
    # Get the Claude Desktop config file path
    config_path = get_claude_desktop_config_path()
    
    if not config_path:
        raise ValueError("Could not find Claude Desktop config file")
        
    # Read the existing config
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        config = {}
        
    # Initialize mcpServers if it doesn't exist
    if "mcpServers" not in config:
        config["mcpServers"] = {}
        
    # Prepare the server config
    server_config = {
        "command": command,
        "args": args,
    }
    
    # Add environment variables if provided
    if env and len(env) > 0:
        server_config["env"] = parse_env_vars(env)
                
    # Add working directory if provided
    if cwd:
        server_config["cwd"] = cwd
        
    # Add the server to the config
    config["mcpServers"][server_name] = server_config
    
    # Write the config back to the file
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

@mcp.tool()
def install_repo_mcp_server(
    name: str, 
    args: Optional[List[str]] = None,
    env: Optional[List[str]] = None,
) -> str:
    """
    Install an MCP server via pip or npm.
    
    Args:
        name: The package name of the MCP server
        args: The arguments to pass along
        env: The environment variables to set, delimited by =
    """
    if args is None:
        args = []
        
    # Check if Node.js is installed (for npm packages)
    has_node = check_command_exists("node")
    has_npm = check_command_exists("npm")
    has_npx = check_command_exists("npx")
    has_pip = check_command_exists("pip")
    has_python = check_command_exists("python")
    
    if not has_node and not has_python:
        return "Neither Node.js nor Python is installed. Please install one of them."
    
    # Determine if this is likely an npm package (starts with @ or doesn't have dots)
    is_likely_npm_package = name.startswith('@') or '.' not in name
    
    # Handle npm packages
    if has_npm and has_npx and is_likely_npm_package:
        # Extract server name from package name (handle scoped packages)
        if name.startswith("@") and "/" in name:
            # For @scope/package, use just "package" as the server name
            server_name = name.split("/")[1]
        else:
            server_name = name
            
        # Install to Claude Desktop using npx directly
        install_to_claude_desktop(
            server_name,
            "npx",
            [name] + args,
            env,
        )
        
        return f"Successfully installed MCP server '{server_name}' via npx! Please tell the user to restart the application."
        
    # Handle Python packages (likely has dots in the name)
    if has_pip and has_python and '.' in name:
        # For Python packages, use the package name directly
        server_name = name
        
        # Install to Claude Desktop
        install_to_claude_desktop(
            server_name,
            "python",
            ["-m", name] + args,
            env,
        )
        
        return f"Successfully installed MCP server '{server_name}' via Python! Please tell the user to restart the application."
    
    # If we can't determine the type, try npm first if available, then Python
    if has_npm and has_npx:
        # Use the last part of the name as the server name
        if "/" in name:
            server_name = name.split("/")[-1]
        else:
            server_name = name
            
        install_to_claude_desktop(
            server_name,
            "npx",
            [name] + args,
            env,
        )
        
        return f"Successfully installed MCP server '{server_name}' via npx! Please tell the user to restart the application."
    elif has_pip and has_python:
        server_name = name.split(".")[-1] if "." in name else name
        
        install_to_claude_desktop(
            server_name,
            "python",
            ["-m", name] + args,
            env,
        )
        
        return f"Successfully installed MCP server '{server_name}' via Python! Please tell the user to restart the application."
        
    return f"Could not determine how to install '{name}'"

@mcp.tool()
def install_local_mcp_server(
    path: str, 
    args: Optional[List[str]] = None,
    env: Optional[List[str]] = None,
) -> str:
    """
    Install an MCP server from a local directory.
    
    Args:
        path: The path to the MCP server code cloned on your computer
        args: The arguments to pass along
        env: The environment variables to set, delimited by =
    """
    if args is None:
        args = []
        
    if not os.path.exists(path):
        return f"Path '{path}' does not exist."
        
    # Check if it's a Node.js or Python project
    has_package_json = os.path.exists(os.path.join(path, "package.json"))
    has_pyproject_toml = os.path.exists(os.path.join(path, "pyproject.toml"))
    has_setup_py = os.path.exists(os.path.join(path, "setup.py"))
    
    # Determine server name from directory name
    server_name = os.path.basename(path)
    
    # Check if Node.js is installed (for npm packages)
    has_node = check_command_exists("node")
    has_npm = check_command_exists("npm")
    has_pip = check_command_exists("pip")
    has_python = check_command_exists("python")
    
    # Handle Node.js projects
    if has_package_json and has_node and has_npm:
        # For Node.js projects, use node directly to run the local script
        # Find the main entry point from package.json
        try:
            with open(os.path.join(path, "package.json"), "r") as f:
                package_json = json.load(f)
                
            # Try to find the main entry point
            main_file = package_json.get("main", "index.js")
            
            # Install to Claude Desktop
            install_to_claude_desktop(
                server_name,
                "node",
                [os.path.join(path, main_file)] + args,
                env,
            )
            
            return f"Successfully installed local Node.js MCP server '{server_name}'! Please tell the user to restart the application."
        except Exception as e:
            return f"Error installing Node.js MCP server: {str(e)}"
            
    # Handle Python projects
    elif (has_pyproject_toml or has_setup_py) and has_python:
        # For Python projects, use python -m to run the module
        # Try to determine the module name from directory structure
        module_name = server_name.replace("-", "_")
        
        # Check if there's a directory with the same name
        if os.path.isdir(os.path.join(path, module_name)):
            # Install to Claude Desktop
            install_to_claude_desktop(
                server_name,
                "python",
                ["-m", module_name] + args,
                env,
                cwd=path,
            )
            
            return f"Successfully installed local Python MCP server '{server_name}'! Please tell the user to restart the application."
        else:
            # Try to find any Python files in the root directory
            py_files = [f for f in os.listdir(path) if f.endswith(".py") and f != "setup.py"]
            
            if py_files:
                main_file = py_files[0].replace(".py", "")
                
                # Install to Claude Desktop
                install_to_claude_desktop(
                    server_name,
                    "python",
                    [os.path.join(path, main_file + ".py")] + args,
                    env,
                )
                
                return f"Successfully installed local Python MCP server '{server_name}'! Please tell the user to restart the application."
    
    return f"Could not determine how to install MCP server from '{path}'. Make sure it's a valid Node.js or Python project."

def main():
    """Run the MCP Builder server."""
    mcp.run()

if __name__ == "__main__":
    main()