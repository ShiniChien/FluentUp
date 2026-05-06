from googletrans import Translator
translator = Translator(
    service_urls = [
    	'translate.googleapis.com'
	]
)

async def translate_text():
	async with Translator() as translator:
		result = await translator.translate('drought', dest='vi', src='en')
		print(result)

if __name__ == "__main__":
    import asyncio
    asyncio.run(translate_text())
    