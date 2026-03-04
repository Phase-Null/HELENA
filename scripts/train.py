import sys
import argparse

def main():
    parser = argparse.ArgumentParser(description='Training control script')
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Enable autonomous training
    subparsers.add_parser('enable', help='Enable autonomous training (with default schedule)')
    
    # Disable training
    subparsers.add_parser('disable', help='Disable training')
    
    # Start manual session
    start_parser = subparsers.add_parser('start', help='Start a manual session now')
    start_parser.add_argument('--focus', nargs='+', help='Focus area (e.g., code efficiency)')
    
    # Show training status
    subparsers.add_parser('status', help='Show training status and last report')
    
    # Generate report
    report_parser = subparsers.add_parser('report', help='Generate a report for the last N days')
    report_parser.add_argument('--days', type=int, help='Number of days to report')
    
    args = parser.parse_args()
    
    if args.command == 'enable':
        print('Enabling autonomous training...')
    elif args.command == 'disable':
        print('Disabling training...')
    elif args.command == 'start':
        print(f'Starting manual session (focus: {args.focus})')
    elif args.command == 'status':
        print('Training status and last report...')
    elif args.command == 'report':
        print(f'Generating report for last {args.days} days...')
    else:
        parser.print_help()

if __name__ == '__main__':
    main()