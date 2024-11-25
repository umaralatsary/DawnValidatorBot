import requests
import json
import logging
import time
import asyncio
import telegram
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
import colorlog
from colorama import init, Fore, Back, Style
from fake_useragent import UserAgent
import urllib3
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from asyncio import Queue
import itertools
import argparse

banner = """
==================================================================
 █████╗ ██╗██████╗ ██████╗ ██████╗  ██████╗ ██████╗ 
██╔══██╗██║██╔══██╗██╔══██╗██╔══██╗██╔═══██╗██╔══██╗
███████║██║██████╔╝██║  ██║██████╔╝██║   ██║██████╔╝
██╔══██║██║██╔══██╗██║  ██║██╔══██╗██║   ██║██╔═══╝ 
██║  ██║██║██║  ██║██████╔╝██║  ██║╚██████╔╝██║     
╚═╝  ╚═╝╚═╝╚═╝  ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚═╝     
                                                    
██╗███╗   ██╗███████╗██╗██████╗ ███████╗██████╗     
██║████╗  ██║██╔════╝██║██╔══██╗██╔════╝██╔══██╗    
██║██╔██╗ ██║███████╗██║██║  ██║█████╗  ██████╔╝    
██║██║╚██╗██║╚════██║██║██║  ██║██╔══╝  ██╔══██╗    
██║██║ ╚████║███████║██║██████╔╝███████╗██║  ██║    
╚═╝╚═╝  ╚═══╝╚══════╝╚═╝╚═════╝ ╚══════╝╚═╝  ╚═╝    

Join our Telegram channel for the latest updates: t.me/airdropinsiderid

DAWN AUTO BOT - Airdrop Insider
==================================================================
"""
print(banner)
time.sleep(1)

def parse_arguments():
    """
    Parse command-line arguments.

    Returns:
        argparse.Namespace: Parsed arguments.
    """
    parser = argparse.ArgumentParser(description='Dawn Auto Bot with multiple workers')
    parser.add_argument('--worker', '-w', '-W', type=int, default=3, 
                       help='Number of concurrent workers (min: 1)')
    args = parser.parse_args()
    if args.worker < 1:
        parser.error("Number of workers must be at least 1")
    return args

CONFIG_FILE = "config.json"
PROXY_FILE = "proxies.txt"

# Setup logging with color
log_colors = {
    'DEBUG': 'cyan',
    'INFO': 'white',
    'WARNING': 'yellow',
    'ERROR': 'red',
    'SUCCESS': 'green'
}

formatter = colorlog.ColoredFormatter(
    "%(log_color)s%(asctime)s - %(levelname)s - %(message)s",
    log_colors=log_colors
)

handler = logging.StreamHandler()
handler.setFormatter(formatter)

logger = logging.getLogger()
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Adding a custom SUCCESS level between INFO and WARNING
SUCCESS_LEVEL = 25
logging.addLevelName(SUCCESS_LEVEL, "SUCCESS")

def log_success(message, *args, **kwargs):
    if logger.isEnabledFor(SUCCESS_LEVEL):
        logger._log(SUCCESS_LEVEL, message, args, **kwargs)

logging.success = log_success

def read_config(filename=CONFIG_FILE):
    try:
        with open(filename, 'r') as file:
            config = json.load(file)
        return config
    except FileNotFoundError:
        logging.error(f"Configuration file '{filename}' not found.")
        return {}
    except json.JSONDecodeError:
        logging.error(f"Invalid JSON format in '{filename}'.")
        return {}

def parse_proxy(proxy):
    """Parse proxy string into format for requests."""
    proxy_url = urlparse(proxy)
    if proxy_url.scheme in ['http', 'https', 'socks5']:
        if proxy_url.username and proxy_url.password:
            return {
                'http': f"{proxy_url.scheme}://{proxy_url.username}:{proxy_url.password}@{proxy_url.hostname}:{proxy_url.port}",
                'https': f"{proxy_url.scheme}://{proxy_url.username}:{proxy_url.password}@{proxy_url.hostname}:{proxy_url.port}",
            }
        else:
            return {
                'http': f"{proxy_url.scheme}://{proxy_url.hostname}:{proxy_url.port}",
                'https': f"{proxy_url.scheme}://{proxy_url.hostname}:{proxy_url.port}",
            }
    return {}

def read_proxies(filename=PROXY_FILE):
    proxies = []
    try:
        with open(filename, 'r') as file:
            for line in file:
                proxy = line.strip()
                if proxy:
                    proxies.append(proxy)
    except FileNotFoundError:
        logging.error(f"Proxy file '{filename}' not found.")
    return proxies

def check_proxy(proxy):
    """Check if the proxy is active by sending a request to a test URL."""
    proxies = parse_proxy(proxy)
    test_url = "http://httpbin.org/ip"  # You can change this URL to any service that returns IP
    try:
        response = requests.get(test_url, proxies=proxies, timeout=5)
        if response.status_code == 200:
            logging.success(f"Proxy {proxy} is active.")
            return True
    except requests.RequestException:
        logging.error(f"Proxy {proxy} is inactive.")
    return False

def get_active_proxies():
    proxies = read_proxies(PROXY_FILE)
    active_proxies = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(check_proxy_silent, proxy) for proxy in proxies]
        for future, proxy in zip(futures, proxies):
            if future.result():
                active_proxies.append(proxy)
    if not active_proxies:
        logging.error("No active proxies found. Exiting...")
        exit(1)
    return active_proxies

def check_proxy_silent(proxy):
    """Check if the proxy is active without logging."""
    proxies = parse_proxy(proxy)
    test_url = "http://httpbin.org/ip"
    try:
        response = requests.get(test_url, proxies=proxies, timeout=5)
        return response.status_code == 200
    except:
        return False

def update_proxies_file(active_proxies):
    """Update proxies.txt file with only active proxies."""
    with open(PROXY_FILE, 'w') as file:
        for proxy in active_proxies:
            file.write(f"{proxy}\n")
    logging.success(f"Updated {PROXY_FILE} with {len(active_proxies)} active proxies.")

def create_session(proxy_queue):
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(
        max_retries=retry_strategy,
        pool_connections=10, 
        pool_maxsize=10
    )
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    session.timeout = (5, 10)  # (connect timeout, read timeout)
    
    proxy = proxy_queue.get()
    proxies = parse_proxy(proxy)
    logging.info(f"Using proxy: {proxy}")
    session.proxies.update(proxies)
    
    return session, proxy_queue

config = read_config(CONFIG_FILE)
bot_token = config.get("telegram_bot_token")
chat_id = config.get("telegram_chat_id")
use_proxy = config.get("use_proxy", False)
use_telegram = config.get("use_telegram", False)
poll_interval = config.get("poll_interval", 120)  # Default to 120 seconds

if use_telegram and (not bot_token or not chat_id):
    logging.error("Missing 'bot_token' or 'chat_id' in 'config.json'.")
    exit(1)

bot = telegram.Bot(token=bot_token) if use_telegram else None
keepalive_url = "https://www.aeropres.in/chromeapi/dawn/v1/userreward/keepalive"
get_points_url = "https://www.aeropres.in/api/atom/v1/userreferral/getpoint"
extension_id = "fpdkjdnhkakefebpekbdhillbhonfjjp"
_v = "1.0.7"

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
ua = UserAgent()

def read_account(filename="config.json"):
    try:
        with open(filename, 'r') as file:
            data = json.load(file)
            accounts = data.get("accounts", [])
            return accounts 
    except FileNotFoundError:
        logging.error(f"Config file '{filename}' not found.")
        return []
    except json.JSONDecodeError:
        logging.error(f"Invalid JSON format in '{filename}'.")
        return []

async def total_points(headers, session):
    num_retries = 3
    for retry in range(num_retries):
        try:
            response = await session.get(get_points_url, headers=headers, verify=False)
            response.raise_for_status()

            json_response = await response.json()
            if json_response.get("status"):
                reward_point_data = json_response["data"]["rewardPoint"]
                referral_point_data = json_response["data"]["referralPoint"]
                total_points = (
                    reward_point_data.get("points", 0) +
                    reward_point_data.get("registerpoints", 0) +
                    reward_point_data.get("signinpoints", 0) +
                    reward_point_data.get("twitter_x_id_points", 0) +
                    reward_point_data.get("discordid_points", 0) +
                    reward_point_data.get("telegramid_points", 0) +
                    reward_point_data.get("bonus_points", 0) +
                    referral_point_data.get("commission", 0)
                )
                return total_points
            else:
                logging.warning(f"Warning: {json_response.get('message', 'Unknown error when fetching points')}")
        except requests.exceptions.RequestException as e:
            if retry == num_retries - 1:
                logging.error(f"Error fetching points: {e}")
            else:
                logging.warning(f"Failed to fetch points, retrying... ({retry+1}/{num_retries})")
                await asyncio.sleep(5)  # Delay before retrying
    return 0

def keep_alive(headers, email, session):
    keepalive_payload = {
        "username": email,
        "extensionid": extension_id,
        "numberoftabs": 0,
        "_v": _v
    }

    headers["User-Agent"] = ua.random

    try:
        response = session.post(keepalive_url, headers=headers, json=keepalive_payload, verify=False)
        response.raise_for_status()

        json_response = response.json()
        if 'message' in json_response:
            return True, json_response['message']
        else:
            return False, "Message not found in response"
    except requests.exceptions.RequestException as e:
        return False, str(e)

# Queue for Telegram messages
message_queue = Queue()

async def telegram_worker():
    while True:
        message = await message_queue.get()
        await telegram_message(message)
        message_queue.task_done()

async def queue_telegram_message(message):
    await message_queue.put(message)

async def telegram_message(message):
    if use_telegram:
        num_retries = 3
        for retry in range(num_retries):
            try:
                await bot.send_message(chat_id=chat_id, text=message, parse_mode="Markdown")
                await asyncio.sleep(1)  # Delay of 1 second after sending the message
                break
            except Exception as e:
                if retry == num_retries - 1:
                    logging.error(f"Error sending Telegram message: {e}")
                else:
                    logging.warning(f"Failed to send Telegram message, retrying... ({retry+1}/{num_retries})")
                    await asyncio.sleep(5)  # Delay before retrying

class AccountWorker:
    def __init__(self, accounts, worker_id, proxy_queue):
        self.accounts = accounts
        self.worker_id = worker_id
        self.proxy_queue = proxy_queue
        self.running = True
        self.stats = {
            "success": 0,
            "failed": 0,
            "total_processed": 0
        }

    async def run(self):
        while self.running:
            try:
                # Membuat tasks untuk semua akun sekaligus
                tasks = []
                for account in self.accounts:
                    task = asyncio.create_task(self.process_account(account))
                    tasks.append(task)
                
                # Menjalankan semua tasks secara bersamaan
                await asyncio.gather(*tasks)
                
                self.stats["total_processed"] += len(self.accounts)
                logging.info(f"Worker {self.worker_id} stats: {self.stats}")
                await asyncio.sleep(poll_interval)
            except Exception as e:
                logging.error(f"Worker {self.worker_id} error: {str(e)}")
                await asyncio.sleep(poll_interval)

    async def process_account(self, account):
        email = account["email"]
        token = account["token"]
        
        headers = { 
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": ua.random
        }

        session, self.proxy_queue = create_session(self.proxy_queue)
        try:
            success, status_message = await keep_alive(headers, email, session)
                if success:
                    points = await total_points(headers, session)
                    message = (
                        "✅ *🌟 Success Notification 🌟* ✅\n\n"
                        f"👤 *Account:* {email}\n\n"
                        f"💰 *Points Earned:* {points}\n\n"
                        f"📢 *Message:* {status_message}\n\n"
                        f"🛠️ *Proxy Used:* {proxy}\n\n"
                        "🤖 *Bot made by https://t.me/AirdropInsiderID*"
                    )
                    await telegram_message(message)
                    logging.info(f"Worker {self.worker_id} - Account {email}: Success")
                    self.stats["success"] += 1
                    success_count += 1
                    if success_count >= 1:
                        return True
                else:
                    logging.error(f"Worker {self.worker_id} - Failed keep alive for {email}. Retry {retry+1}/{max_retries}")
                    fail_count += 1
                    if fail_count >= 10:
                        self.stats["failed"] += 1
                        message = (
                            "⚠️ *Failure Notification* ⚠️\n\n"
                            f"👤 *Account:* {email}\n\n"
                            "❌ *Status:* Keep Alive Failed\n\n"
                            "⚙️ *Action Required:* Please check account status.\n\n"
                            "🤖 *Bot made by https://t.me/AirdropInsiderID*"
                        )
                        await telegram_message(message)
                        break
            
            except Exception as e:
                logging.error(f"Worker {self.worker_id} - Error processing {email}: {str(e)}")
                fail_count += 1
                if fail_count >= 10:
                    self.stats["failed"] += 1
                    message = (
                        "⚠️ *Failure Notification* ⚠️\n\n"
                        f"👤 *Account:* {email}\n\n"
                        "❌ *Status:* Keep Alive Failed\n\n"
                        "⚙️ *Action Required:* Please check account status.\n\n"
                        "🤖 *Bot made by https://t.me/AirdropInsiderID*"
                    )
                    await telegram_message(message)
                    break
            finally:
            session.close()
            self.proxy_queue.put(session.proxies['http'].split('://')[1])
        return False
        
async def keep_alive(headers, email, session):
    keepalive_payload = {
        "username": email,
        "extensionid": extension_id,
        "numberoftabs": 0,
        "_v": _v
    }

    headers["User-Agent"] = ua.random

    try:
        response = await session.post(keepalive_url, headers=headers, json=keepalive_payload, verify=False)
        response.raise_for_status()

        json_response = await response.json()
        if 'message' in json_response:
            return True, json_response['message']
        else:
            return False, "Message not found in response"
    except requests.exceptions.RequestException as e:
        return False, str(e)

async def total_points(headers, session):
    try:
        response = await session.get(get_points_url, headers=headers, verify=False)
        response.raise_for_status()

        json_response = await response.json()
        if json_response.get("status"):
            reward_point_data = json_response["data"]["rewardPoint"]
            referral_point_data = json_response["data"]["referralPoint"]
            total_points = (
                reward_point_data.get("points", 0) +
                reward_point_data.get("registerpoints", 0) +
                reward_point_data.get("signinpoints", 0) +
                reward_point_data.get("twitter_x_id_points", 0) +
                reward_point_data.get("discordid_points", 0) +
                reward_point_data.get("telegramid_points", 0) +
                reward_point_data.get("bonus_points", 0) +
                referral_point_data.get("commission", 0)
            )
            return total_points
        else:
            logging.warning(f"Warning: {json_response.get('message', 'Unknown error when fetching points')}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching points: {e}")
    return 0

def setup_logging(log_file=None):
    log_colors = {
        'DEBUG': 'cyan',
        'INFO': 'white',
        'WARNING': 'yellow',
        'ERROR': 'red',
        'SUCCESS': 'green'
    }

    formatter = colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s - %(levelname)s - %(message)s",
        log_colors=log_colors
    )

    handlers = [logging.StreamHandler()]
    if log_file:
        handlers.append(logging.FileHandler(log_file))

    for handler in handlers:
        handler.setFormatter(formatter)

    logger = logging.getLogger()
    logger.handlers.clear()
    for handler in handlers:
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    logging.success = log_success

async def main():
    args = parse_arguments()
    num_workers = args.worker
    poll_interval = config.get("poll_interval", 120)
    log_file = args.log_file
    
    setup_logging(log_file)
    
    if not accounts:
        logging.error("No accounts found in configuration.")
        return

    # Proses proxy hanya sekali di awal
    active_proxies = get_active_proxies()
    if not active_proxies:
        logging.error("No active proxies found. Exiting...")
        return
    
    update_proxies_file(active_proxies)
    
    # Membuat dan menjalankan semua worker sekaligus
    workers = []
    tasks = []
    
    # Membagi akun ke semua worker
    accounts_per_worker = len(accounts) // num_workers
    remainder = len(accounts) % num_workers
    start_idx = 0
    
    for i in range(num_workers):
        count = accounts_per_worker + (1 if i < remainder else 0)
        worker_accounts = accounts[start_idx:start_idx + count]
        start_idx += count
        
        if worker_accounts:
            worker = AccountWorker(worker_accounts, i+1, active_proxies)
            workers.append(worker)
            tasks.append(worker.run())

    # Menjalankan telegram worker
    telegram_worker_task = asyncio.create_task(telegram_worker())

    # Menjalankan semua worker sekaligus
    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        logging.info("Shutting down...")
    finally:
        # Tunggu semua pesan telegram terkirim
        if not message_queue.empty():
            await message_queue.join()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
