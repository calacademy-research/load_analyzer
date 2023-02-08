const puppeteer = require('puppeteer');

(async () => {
  const browser = await puppeteer.launch({
    headless: true,
    args: ['--no-sandbox']
  });
  const page = await browser.newPage();
  const address = process.argv[2];

  try {
    await page.goto(address, {
      waitUntil: 'networkidle0'
    });
    const content = await page.content();
    console.log(content);
  } catch (error) {
    console.error('Unable to load the address!');
  } finally {
    await browser.close();
  }
})();
