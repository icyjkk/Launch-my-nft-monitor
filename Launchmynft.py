import requests
import json
import os
import discord
from discord.ext import commands, tasks
import time
import asyncio

# Configure the Discord bot
TOKEN = '' #eplace with bot token
CHANNEL_ID = 1277352562718384864  # Replace with the ID of the channel where you want the bot to operate
CODE_FILE = 'last_code.txt'
MONITOR_FILE = 'monitored_collections.json'
webhook_url = ''  # Replace this with your Discord webhook URL
limit = 20  # when these many NFTs are minted, the webhook will trigger
wait = 10  # delay between each request

# Global variable that stores the fixed part of the URL before /collections/
BASE_URL_PART = "https://www.launchmynft.io/_next/data/nTDt3Ms3nBDZEcuC0NfZg/collections/"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)


# Function to save the code to a file
def save_last_code(code):
    with open(CODE_FILE, 'w') as f:
        f.write(code)

# Function to load the last code from a file
def load_last_code():
    if os.path.exists(CODE_FILE):
        with open(CODE_FILE, 'r') as f:
            return f.read().strip()
    return None

# Load monitoring state from a JSON file
def load_monitored_collections():
    if os.path.exists(MONITOR_FILE):
        with open(MONITOR_FILE, 'r') as f:
            return json.load(f)
    return {}

# Save monitoring state to a JSON file
def save_monitored_collections(monitored_collections):
    with open(MONITOR_FILE, 'w') as f:
        json.dump(monitored_collections, f, indent=4)

def send_error_webhook(webhook_url, url, error_message):
    embed = {
        "title": "Error fetching collection data",
        "description": f"There was an error trying to fetch collection data from {url}.",
        "color": 15158332,  # Red
        "fields": [
            {"name": "Error", "value": error_message, "inline": False},
        ],
    }

    data = {
        "content": "⚠️ Error fetching collection data.",
        "embeds": [embed],
    }

    response = requests.post(webhook_url, json=data)
    if response.status_code == 204:
        print("Error sent successfully to Discord.")
    else:
        print(f"Error sending error message to Discord: {response.status_code}")

# Initialize monitoring state
monitored_collections = load_monitored_collections()

# Function to fetch collection data from a URL
def get_collection_data(url):
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raises an error if the request is unsuccessful
        return response.json()['pageProps']['collection']
    except requests.exceptions.RequestException as e:
        print(f"Error fetching collection data: {e}")
        send_error_webhook(webhook_url, url, str(e))  # Send the error to the webhook
        return None

# Function to send a webhook to Discord
def send_webhook(webhook_url, collection_name, current_mints, max_supply, fraction_minted, original_url):
    embed = {
        "title": f"Alert: {collection_name} Minted!",
        "description": f"{limit} or more additional NFTs have been minted.",
        "color": 15158332,  # Red, you can change it if you want
        "fields": [
            {"name": "Total Minted", "value": str(current_mints), "inline": True},
            {"name": "Max Supply", "value": str(max_supply), "inline": True},
            {"name": "Fraction Minted", "value": f"{fraction_minted*100:.2f}%", "inline": True},
            {"name": "Link", "value": original_url, "inline": False},
        ],
    }

    data = {
        "content": "🚨 New Mint Alert! 🚨",
        "embeds": [embed],
    }

    response = requests.post(webhook_url, json=data)
    if response.status_code == 204:
        print("Alert sent successfully to Discord.")
    else:
        print(f"Error sending alert to Discord: {response.status_code}")

# Function that monitors a collection
async def monitor_collection(ctx, collection_key, collection_data, webhook_url, original_url):
    global BASE_URL_PART  # Ensure the updated global variable is used

    collection_name = collection_data['collectionName']
    last_mints = collection_data['totalMints']

    print(f"Starting monitoring of the collection '{collection_name}'")

    while True:
        transformed_url = BASE_URL_PART + collection_key  # Build the URL in each iteration
        print(f"Using URL: {transformed_url}")
        
        await asyncio.sleep(wait)  # Wait between each check asynchronously
        
        # Verify and update data
        updated_data = get_collection_data(transformed_url)
        if updated_data:
            current_mints = updated_data['totalMints']
            max_supply = updated_data['maxSupply']
            fraction_minted = current_mints / max_supply

            # Progress message
            progress_message = f"Monitoring '{collection_name}': {current_mints}/{max_supply} NFTs minted ({fraction_minted*100:.2f}%)."
            print(progress_message)

            # Check if 100 additional NFTs have been minted
            if current_mints - last_mints >= limit:
                print(f"The limit of {limit} NFTs minted in '{collection_name}' has been reached. Sending alert.")
                send_webhook(webhook_url, collection_name, current_mints, max_supply, fraction_minted, original_url)
                last_mints = current_mints  # Update for the next check

                # Update the monitoring file
                monitored_collections[collection_key]['collection_data']['totalMints'] = current_mints
                save_monitored_collections(monitored_collections)

            # Check if it's 100% minted
            if fraction_minted >= 1.0:
                completion_message = f"'{collection_name}' is fully minted! Ending monitoring."
                print(completion_message)
                if ctx:
                    await ctx.send(completion_message)
                del monitored_collections[collection_key]  # Remove from the monitored list
                save_monitored_collections(monitored_collections)
                break

# Function to transform the URL and get the key
def get_collection_key(original_url: str) -> str:
    collection_key = original_url.split('/collections/')[-1] + '.json'
    return collection_key

# Discord command to start monitoring a link
@bot.command(name='monitor')
async def monitor(ctx, url: str):
    global BASE_URL_PART  # Ensure the updated global variable is used

    if 'launchmynft.io' not in url:
        await ctx.send("Please provide a valid LaunchMyNFT link.")
        print("Invalid link provided.")
        return

    collection_key = get_collection_key(url)

    if collection_key in monitored_collections:
        await ctx.send("This link is already being monitored.")
        print(f"Link already monitored: {url}")
        return

    # Create the complete transformed URL
    transformed_url = BASE_URL_PART + collection_key

    # Get collection data
    collection_data = get_collection_data(transformed_url)
    if not collection_data:
        await ctx.send("Could not fetch collection information. Check the link.")
        print(f"Error fetching collection data with URL: {transformed_url}")
        return

    # Save the collection in the dictionary and start monitoring it
    monitored_collections[collection_key] = {
        "collection_data": collection_data,
        "original_url": url  # Save the original URL
    }
    save_monitored_collections(monitored_collections)
    await ctx.send(f"Starting to monitor '{collection_data['collectionName']}'.")

    print(f"Started monitoring the collection '{collection_data['collectionName']}'.")

    # Start monitoring in the background
    bot.loop.create_task(monitor_collection(ctx, collection_key, collection_data, webhook_url, url))

# Discord command to list the collections being monitored
@bot.command(name='list')
async def list_monitored(ctx):
    global BASE_URL_PART  # Ensure the updated global variable is used

    if not monitored_collections:
        await ctx.send("No collections are currently being monitored.")
        print("No collections are being monitored.")
    else:
        monitored_list = '\n'.join([f"{data['collection_data']['collectionName']} - https://launchmynft.io/collections/{key.replace('.json', '')}" for key, data in monitored_collections.items()])
        await ctx.send(f"The following collections are being monitored:\n{monitored_list}")
        print(f"Monitored collections:\n{monitored_list}")

# Command to update the base part of the URL
@bot.command(name='change')
async def update_base_url(ctx, new_code: str):
    global BASE_URL_PART
    BASE_URL_PART = f"https://www.launchmynft.io/_next/data/{new_code}/collections/"
    save_last_code(new_code)  # Save the code to a file
    await ctx.send(f"The base URL has been updated to: {BASE_URL_PART}")
    print(f"The base URL has been updated to: {BASE_URL_PART}")

# Discord command to stop the bot
@bot.command(name='stop')
async def stop_bot(ctx):
    await ctx.send("Stopping bot...")
    print("Bot stopped by command.")
    await bot.close()

# Event to notify when the bot is ready
@bot.event
async def on_ready():
    global BASE_URL_PART
    last_code = load_last_code()
    if last_code:
        BASE_URL_PART = f"https://www.launchmynft.io/_next/data/{last_code}/collections/"
        print(f"Base URL initialized with the last code: {BASE_URL_PART}")
    else:
        print("No previous code found. Using the default code.")
    
    print(f'Bot connected as {bot.user}')
    
    # Restart monitoring of previously saved collections
    for collection_key, data in monitored_collections.items():
        print(f"Restarting monitoring of the collection '{data['collection_data']['collectionName']}'")
        bot.loop.create_task(monitor_collection(None, collection_key, data['collection_data'], webhook_url))

# Command to remove a collection from monitoring
@bot.command(name='remove')
async def remove_collection(ctx, url: str):
    collection_key = get_collection_key(url)

    if collection_key in monitored_collections:
        del monitored_collections[collection_key]
        save_monitored_collections(monitored_collections)
        await ctx.send(f"The collection with URL '{url}' has been removed from monitoring.")
        print(f"Removed from monitoring the collection with URL: {url}")
    else:
        await ctx.send(f"No collection found in monitoring with that URL.")
        print(f"No collection found in monitoring with the URL: {url}")

# Start the Discord bot
bot.run(TOKEN)
