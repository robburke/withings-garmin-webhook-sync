"""
Webhook Manager - Utility for managing Withings webhook subscriptions
"""
import sys
import logging
import argparse
from config import Config
from withings_client import WithingsClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def list_webhooks(client: WithingsClient):
    """List all active webhook subscriptions"""
    print("\n" + "=" * 80)
    print("ACTIVE WEBHOOK SUBSCRIPTIONS")
    print("=" * 80 + "\n")

    webhooks = client.list_webhooks()

    if not webhooks:
        print("No active webhooks found.\n")
    else:
        for i, webhook in enumerate(webhooks, 1):
            print(f"{i}. {webhook}")

    print("=" * 80 + "\n")


def subscribe_webhook(client: WithingsClient, callback_url: str):
    """Subscribe to webhook notifications"""
    print(f"\nSubscribing to webhook with URL: {callback_url}")

    if not callback_url.startswith('https://'):
        print("\n[WARNING] Withings requires HTTPS URLs for webhooks!")
        print("Make sure your URL uses HTTPS\n")

        response = input("Continue anyway? (y/n): ").strip().lower()
        if response != 'y':
            print("Aborted.")
            return False

    try:
        client.subscribe_webhook(callback_url)
        print("\n[OK] Successfully subscribed to webhook!")
        print(f"\nWithings will now send notifications to: {callback_url}")
        return True

    except Exception as e:
        print(f"\n[FAIL] Failed to subscribe: {str(e)}")
        return False


def unsubscribe_webhook(client: WithingsClient, callback_url: str):
    """Unsubscribe from webhook notifications"""
    print(f"\nUnsubscribing from webhook: {callback_url}")

    try:
        client.unsubscribe_webhook(callback_url)
        print("\n[OK] Successfully unsubscribed from webhook!")
        return True

    except Exception as e:
        print(f"\n[FAIL] Failed to unsubscribe: {str(e)}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Manage Withings webhook subscriptions',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List active webhooks
  python webhook_manager.py list

  # Subscribe to webhook (use your Lambda API Gateway URL)
  python webhook_manager.py subscribe https://j7ebm5kb9l.execute-api.ca-central-1.amazonaws.com/prod/webhook/withings

  # Unsubscribe from webhook
  python webhook_manager.py unsubscribe https://j7ebm5kb9l.execute-api.ca-central-1.amazonaws.com/prod/webhook/withings
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # List command
    subparsers.add_parser('list', help='List all active webhooks')

    # Subscribe command
    subscribe_parser = subparsers.add_parser('subscribe', help='Subscribe to webhook notifications')
    subscribe_parser.add_argument('url', help='Your Lambda API Gateway HTTPS callback URL')

    # Unsubscribe command
    unsubscribe_parser = subparsers.add_parser('unsubscribe', help='Unsubscribe from webhook')
    unsubscribe_parser.add_argument('url', help='The callback URL to unsubscribe')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Initialize clients
    try:
        config = Config()
        withings_client = WithingsClient(config)
    except Exception as e:
        print(f"\n[FAIL] Failed to initialize Withings client: {str(e)}")
        print("\nMake sure you have:")
        print("1. Completed initial setup (run: python setup.py)")
        print("2. Set all required environment variables in .env file")
        return

    # Execute command
    if args.command == 'list':
        list_webhooks(withings_client)

    elif args.command == 'subscribe':
        success = subscribe_webhook(withings_client, args.url)
        if success:
            print("\n" + "=" * 80)
            print("NEXT STEPS")
            print("=" * 80)
            print("\n1. Step on your Withings scale!")
            print("2. Check Lambda logs to confirm sync:")
            print("   aws logs tail --log-group-name '/aws/lambda/withings-garmin-sync-prod' --region ca-central-1 --follow")
            print("\n" + "=" * 80 + "\n")

    elif args.command == 'unsubscribe':
        unsubscribe_webhook(withings_client, args.url)


if __name__ == '__main__':
    main()
