import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(r'D:\milu_publish_reverse_20260513\bjh_browser_data', channel='msedge', headless=False, viewport={'width':1400,'height':900})
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        cdp = await ctx.new_cdp_session(page)
        print(type(cdp))
        print([m for m in dir(cdp) if not m.startswith('_')])
        await ctx.close()

asyncio.run(test())