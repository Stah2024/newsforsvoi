from telethon.sync import TelegramClient

api_id = 29950619
api_hash = '85bcb9af365871ca4c8650a756b1ff78'

client = TelegramClient('bot/session', api_id, api_hash)
client.start() 