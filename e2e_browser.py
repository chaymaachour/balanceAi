"""Browser test (optional): python tests/e2e_browser.py http://localhost:5000
Requires `pip install playwright && playwright install chromium` and a RUNNING server with an empty database.
Creates two throw-away accounts (desktop@example.com, mobile@example.com)."""
import asyncio
import sys
from playwright.async_api import async_playwright
B=sys.argv[1] if len(sys.argv)>1 else "http://localhost:5000"
async def main():
    async with async_playwright() as p:
        br=await p.chromium.launch(); out=[]
        for name,vp in (("desktop",{"width":1280,"height":800}),("mobile",{"width":390,"height":780})):
            ctx=await br.new_context(viewport=vp,locale="en-GB"); pg=await ctx.new_page(); errs=[]
            pg.on("pageerror",lambda e:errs.append(str(e)))
            pg.on("console",lambda m:errs.append(m.text) if m.type=="error" and "401" not in m.text and "fonts" not in m.text else None)
            await pg.goto(B); await pg.wait_for_selector(".auth-card")
            out.append(f"{name}: gate shown")
            await pg.click(".auth-switch"); await pg.fill("#authEmail",f"{name}@example.com"); await pg.fill("#authPw","Abcdefghi12"); await pg.fill("#authPw2","Different123")
            await pg.click(".auth-card button[type=submit]"); out.append(name+": mismatch -> "+await pg.inner_text(".auth-error"))
            await pg.fill("#authPw2","Abcdefghi12"); await pg.click(".auth-card button[type=submit]")
            await pg.wait_for_selector("#view-home:not([hidden])"); await pg.wait_for_timeout(600)
            out.append(name+": signed up, gate gone="+str(await pg.locator(".auth-gate").count()==0))
            await pg.click("[data-profile=universite]"); await pg.click("#obForm button[type=submit]"); await pg.wait_for_selector("#onboarding",state="hidden"); out.append(name+": onboarding completed"); await pg.wait_for_timeout(1200)
            await pg.goto(B+"/#chat"); await pg.wait_for_selector("#chatInput")
            await pg.fill("#chatInput","<img src=x onerror=alert(1)> help me plan"); await pg.click("#chatSend")
            await pg.wait_for_selector(".chat-msg.assistant:not(.pending)"); await pg.wait_for_timeout(300)
            out.append(name+": chat reply meta="+await pg.locator(".chat-msg.assistant .chat-meta").last.inner_text())
            out.append(name+": xss img injected="+str(await pg.locator(".chat-bubble img").count()))
            await pg.screenshot(path=f"{name}-chat.png")
            for r in ("calendar","exams","revisions","notifications","settings","history","planner","relax","checkin"):
                await pg.goto(B+"/#"+r); await pg.wait_for_timeout(250)
            await pg.screenshot(path=f"{name}-settings.png")
            await pg.goto(B+"/#home"); await pg.click("#logoutBtn"); await pg.wait_for_selector(".auth-card")
            out.append(name+": signed out -> gate")
            await pg.fill("#authEmail",f"{name}@example.com"); await pg.fill("#authPw","wrongpassword1"); await pg.click(".auth-card button[type=submit]")
            await pg.wait_for_timeout(500); out.append(name+": bad login -> "+await pg.inner_text(".auth-error"))
            await pg.fill("#authPw","Abcdefghi12"); await pg.click(".auth-card button[type=submit]"); await pg.wait_for_selector("#view-home:not([hidden])")
            out.append(name+": onboarding shown again after login="+str(await pg.locator("#onboarding:not([hidden])").count()))
            await pg.goto(B+"/#chat"); await pg.wait_for_timeout(500)
            out.append(name+": history after re-login="+str(await pg.locator(".chat-item").count()))
            out.append(name+": JS errors="+str(errs)); await ctx.close()
        await br.close(); print("\n".join(out))
asyncio.run(main())
