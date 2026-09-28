const PLAYWRIGHT_MCP = {
  browser_click: [
    'mcp_playwright_browser_click',
    `⟦browser_click¦target={str}(¦element={str})?(¦doubleClick={bool})?(¦button={left|right|middle})?(¦modifiers={json})?⟧ — click element (modifiers: JSON array of Alt/Control/ControlOrMeta/Meta/Shift)`,
  ],
  browser_close: ['mcp_playwright_browser_close', `⟦browser_close¦call={true}⟧ — close the page`],
  browser_console_messages: [
    'mcp_playwright_browser_console_messages',
    `⟦browser_console_messages¦level={error|warning|info|debug}(¦all={bool})?(¦filename={str})?⟧ — read console messages`,
  ],
  browser_drag: [
    'mcp_playwright_browser_drag',
    `⟦browser_drag¦startTarget={str}¦endTarget={str}(¦startElement={str})?(¦endElement={str})?⟧ — drag and drop between elements`,
  ],
  browser_drop: [
    'mcp_playwright_browser_drop',
    `⟦browser_drop¦target={str}(¦element={str})?(¦paths={json})?(¦data={json})?⟧ — drop files/data onto element (paths: JSON array of strings; data: JSON object of MIME→string)`,
  ],
  browser_evaluate: [
    'mcp_playwright_browser_evaluate',
    `⟦browser_evaluate¦function={str}(¦element={str})?(¦target={str})?(¦filename={str})?⟧ — run JS on page/element`,
  ],
  browser_file_upload: [
    'mcp_playwright_browser_file_upload',
    `⟦browser_file_upload(¦paths={json})?⟧ — upload file(s) to open chooser (paths: JSON array of strings)`,
  ],
  browser_fill_form: [
    'mcp_playwright_browser_fill_form',
    `⟦browser_fill_form¦fields={json}⟧ — fill multiple form fields (JSON array of {target,name,type,value})`,
  ],
  browser_find: [
    'mcp_playwright_browser_find',
    `⟦browser_find(¦text={str})?(¦regex={str})?⟧ — search page snapshot for text/regex`,
  ],
  browser_handle_dialog: [
    'mcp_playwright_browser_handle_dialog',
    `⟦browser_handle_dialog¦accept={bool}(¦promptText={str})?⟧ — accept/dismiss a dialog`,
  ],
  browser_hover: [
    'mcp_playwright_browser_hover',
    `⟦browser_hover¦target={str}(¦element={str})?⟧ — hover over element`,
  ],
  browser_navigate: [
    'mcp_playwright_browser_navigate',
    `⟦browser_navigate¦url={str}⟧ — navigate to URL`,
  ],
  browser_navigate_back: [
    'mcp_playwright_browser_navigate_back',
    `⟦browser_navigate_back¦call={true}⟧ — go back one page`,
  ],
  browser_network_request: [
    'mcp_playwright_browser_network_request',
    `⟦browser_network_request¦index={int}(¦part={request-headers|request-body|response-headers|response-body})?(¦filename={str})?⟧ — get details of one network request`,
  ],
  browser_network_requests: [
    'mcp_playwright_browser_network_requests',
    `⟦browser_network_requests¦static={bool}(¦filter={str})?(¦filename={str})?⟧ — list network requests since page load`,
  ],
  browser_press_key: [
    'mcp_playwright_browser_press_key',
    `⟦browser_press_key¦key={str}⟧ — press a keyboard key`,
  ],
  browser_resize: [
    'mcp_playwright_browser_resize',
    `⟦browser_resize¦width={int}¦height={int}⟧ — resize browser window`,
  ],
  browser_run_code_unsafe: [
    'mcp_playwright_browser_run_code_unsafe',
    `⟦browser_run_code_unsafe(¦code={str})?(¦filename={str})?⟧ — run raw Playwright JS (RCE-equivalent)`,
  ],
  browser_select_option: [
    'mcp_playwright_browser_select_option',
    `⟦browser_select_option¦target={str}¦values={json}(¦element={str})?⟧ — select dropdown option(s) (values: JSON array of strings)`,
  ],
  browser_snapshot: [
    'mcp_playwright_browser_snapshot',
    `⟦browser_snapshot(¦target={str})?(¦filename={str})?(¦depth={int})?(¦boxes={bool})?⟧ — capture accessibility snapshot`,
  ],
  browser_tabs: [
    'mcp_playwright_browser_tabs',
    `⟦browser_tabs¦action={list|new|close|select}(¦index={int})?(¦url={str})?⟧ — list/open/close/switch tabs`,
  ],
  browser_take_screenshot: [
    'mcp_playwright_browser_take_screenshot',
    `⟦browser_take_screenshot¦type={png|jpeg}¦scale={css|device}(¦element={str})?(¦target={str})?(¦filename={str})?(¦fullPage={bool})?⟧ — screenshot current page`,
  ],
  browser_type: [
    'mcp_playwright_browser_type',
    `⟦browser_type¦target={str}¦text={str}(¦element={str})?(¦submit={bool})?(¦slowly={bool})?⟧ — type text into element`,
  ],
  browser_wait_for: [
    'mcp_playwright_browser_wait_for',
    `⟦browser_wait_for(¦time={int})?(¦text={str})?(¦textGone={str})?⟧ — wait for time/text condition`,
  ],
}

module.exports = PLAYWRIGHT_MCP
