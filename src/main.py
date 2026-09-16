#!/usr/bin/env python3

import argparse
import sys

def main():
    parser = argparse.ArgumentParser(description='Forklift - A command-line tool for managing and deploying applications.')
    parser.add_argument('command', choices=['deploy', 'rollback', 'status'], help='Command to execute')
    parser.add_argument('--platform', help='Cloud platform to deploy to')
    parser.add_argument('--config', help='Configuration file')
    
    args = parser.parse_args()
    
    if args.command == 'deploy':
        print(f"Deploying to {args.platform}")
        # Add deployment logic here
    elif args.command == 'rollback':
        print("Rolling back deployment")
        # Add rollback logic here
    elif args.command == 'status':
        print("Checking deployment status")
        # Add status check logic here

if __name__ == '__main__':
    main()