"""Probe jmseu login page DOM and slider captcha implementation. Temporary."""
from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "https://jmseu-jms.jnt-express.com.cn/login"
ACCOUNT = "01943937"
PASSWORD = "Jt7788521+"
OUT = Path(__file__).parent / "probe_output"
OUT.mkdir(exist_ok=True)


def dump(page, tag):
    page.screenshot(path=str(OUT / f"{tag}.png"), full_page=True)
    (OUT / f"{tag}.html").write_text(page.content(), encoding="utf-8")
    info = page.evaluate(
        """() => {
        const r = {inputs:[], buttons:[], canvases:[], images:[], iframes:[], captcha:[]};
        document.querySelectorAll('input').forEach(el => r.inputs.push({type:el.type,name:el.name,id:el.id,placeholder:el.placeholder,cls:el.className}));
        document.querySelectorAll('button').forEach(el => r.buttons.push({text:(el.innerText||'').trim().slice(0,40),id:el.id,cls:el.className,type:el.type}));
        document.querySelectorAll('canvas').forEach(el => r.canvases.push({id:el.id,cls:el.className,w:el.width,h:el.height}));
        document.querySelectorAll('img').forEach(el => r.images.push({src:(el.src||'').slice(0,140),id:el.id,cls:el.className,alt:el.alt}));
        document.querySelectorAll('iframe').forEach(el => r.iframes.push({src:el.src,id:el.id,cls:el.className}));
        const re=/captcha|verify|slide|slider|puzzle|geetest|tcaptcha|nc_|drag/i;
        document.querySelectorAll('*').forEach(el => {
            const id=el.id||'', cls=String(el.className||'');
            if(re.test(id)||re.test(cls)) r.captcha.push({tag:el.tagName.toLowerCase(),id:el.id,cls:cls.slice(0,120)});
        });
        return r;
    }"""
    )
    print(f"=== {tag} ===")
    print("URL:", page.url, "| TITLE:", page.title())
    print(json.dumps(info, ensure_ascii=False, indent=2))


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel="msedge")
    context = browser.new_context(viewport={"width": 1366, "height": 800})
    context.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
    )
    page = context.new_page()
    page.goto(URL, wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(2500)
    dump(page, "01_initial")

    try:
        page.locator("input[type='text'], input:not([type])").first.fill(
            ACCOUNT, timeout=5000
        )
        print("filled account")
    except Exception as e:
        print("account fill fail:", e)
    try:
        page.locator("input[type='password']").first.fill(PASSWORD, timeout=5000)
        print("filled password")
    except Exception as e:
        print("password fill fail:", e)
    try:
        page.locator(
            "button:has-text('登'), button:has-text('Login'), button:has-text('login'), button[type='submit']"
        ).last.click(timeout=5000)
        print("clicked login")
    except Exception as e:
        print("login click fail:", e)

    page.wait_for_timeout(4000)
    dump(page, "02_after_login_click")
    page.wait_for_timeout(4000)
    dump(page, "03_captcha_wait")
    browser.close()

print("DONE files in", OUT)
