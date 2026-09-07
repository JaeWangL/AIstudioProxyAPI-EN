// The Python Playwright distribution includes this public Node entrypoint.
// Do not import private implementation paths or download a second Node package.
const { firefox } = require(process.cwd());

async function main() {
  let input = '';
  process.stdin.setEncoding('utf8');
  for await (const chunk of process.stdin) input += chunk;
  const options = JSON.parse(Buffer.from(input, 'base64').toString('utf8'));
  if (options.proxy === null) delete options.proxy;
  const server = await firefox.launchServer(options);
  console.log('Websocket endpoint:', server.wsEndpoint());
  let closing = false;
  const close = async () => {
    if (closing) return;
    closing = true;
    await server.close();
  };
  process.once('SIGTERM', close);
  process.once('SIGINT', close);
}

main().catch(error => {
  console.error('Browser server launch failed:', error.message);
  process.exitCode = 1;
});
