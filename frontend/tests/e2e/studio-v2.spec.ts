import {test,expect,type Page} from '@playwright/test';
import path from 'node:path';
const image=(name:string)=>path.resolve(import.meta.dirname,'../../../verification/v02',name);
async function enter(page:Page){await page.goto('/');await page.getByTestId('demo-login').click();await expect(page).toHaveURL(/onboarding/);await page.getByRole('button',{name:'Выбрать первую стратегию',exact:true}).click();await expect(page).toHaveURL(/\/new$/);}

test('Blank graph, manual node, undo, guided same-spec construction, real backtest and causal trace',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));await enter(page);
 await page.getByTestId('create-blank').click();await expect(page).toHaveURL(/\/builder\//);
 const strategyUrl=page.url();
 await expect(page.getByTestId('empty-canvas')).toBeVisible();await expect(page.locator('.react-flow__node')).toHaveCount(0);
 await page.getByTestId('strategy-name').fill('V02 · causal workflow');
 await page.getByTestId('add-node-price').click();await expect(page.locator('.react-flow__node')).toHaveCount(1);
 await page.getByRole('button',{name:'Отменить',exact:true}).click();await expect(page.locator('.react-flow__node')).toHaveCount(0);
 await page.getByRole('button',{name:'Повторить',exact:true}).click();await expect(page.locator('.react-flow__node')).toHaveCount(1);
 await page.getByTestId('save-strategy').click();await expect(page.locator('.save-status')).toContainText('Сохранено');
 await page.getByTestId('guided-builder').click();await expect(page.getByRole('dialog')).toBeVisible();
 await page.getByTestId('wizard-fast').fill('12');await page.getByTestId('wizard-slow').fill('36');await page.getByTestId('wizard-apply').click();
 await expect(page.locator('.react-flow__node')).toHaveCount(7);await page.getByTestId('save-strategy').click();
 await expect(page.locator('.save-status')).toContainText('Сохранено');
 await page.screenshot({path:image('studio-builder-desktop.png'),fullPage:true});
 await page.getByTestId('run-backtest').click();await page.getByTestId('dataset-select').selectOption('demo_btc_4h');
 await page.getByTestId('backtest-start').fill('2023-01-01');await page.getByTestId('backtest-end').fill('2023-12-31');await page.getByTestId('confirm-backtest').click();
 await expect(page).toHaveURL(/\/backtests\//,{timeout:90_000});
 await page.getByTestId('result-tab-terminal').click();
 await expect(page.getByTestId('candlestick-chart')).toBeVisible();await expect(page.getByTestId('trace-event-0')).toBeVisible();
 await page.getByTestId('trace-event-0').click();await expect(page.getByRole('heading',{name:'Что было известно боту',exact:true})).toBeVisible();
 await expect(page.locator('.condition-values')).toBeVisible();await page.screenshot({path:image('studio-trace-desktop.png'),fullPage:true});
 await page.getByTestId('result-tab-scenarios').click();await page.getByTestId('run-scenarios').click();
 await expect(page.getByTestId('scenario-results')).toBeVisible({timeout:90_000});
 await expect(page.getByTestId('scenario-results').locator('thead th')).toHaveCount(4);
 const costCells=page.getByTestId('scenario-results').locator('tbody tr').filter({hasText:'Издержки, USDT'}).locator('td');
 await expect(costCells).toHaveCount(4);
 for(let i=1;i<4;i++)await expect(costCells.nth(i)).not.toHaveText('—');
 await page.screenshot({path:image('studio-scenarios.png'),fullPage:true});
 await page.getByTestId('result-tab-terminal').click();await expect(page.getByTestId('candlestick-chart')).toBeVisible();
 await page.setViewportSize({width:390,height:844});await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
 await page.screenshot({path:image('studio-trace-mobile.png'),fullPage:true});
 await page.setViewportSize({width:1440,height:1000});await page.goto(strategyUrl);
 await page.getByTestId('run-backtest').click();await page.getByTestId('dataset-select').selectOption('demo_btc_4h');
 await page.getByTestId('backtest-start').fill('2023-01-01');await page.getByTestId('backtest-end').fill('2023-12-31');
 await page.getByTestId('execution-mode').selectOption('next_bar_open_optimistic');
 const launched=page.waitForResponse(response=>response.url().endsWith('/api/backtests')&&response.request().method()==='POST');
 await page.getByTestId('confirm-backtest').click();const response=await launched;
 expect(response.status()).toBe(202);expect(response.request().postDataJSON().config.availability_seconds).toBe(0);
 await expect(page).toHaveURL(/\/backtests\//,{timeout:90_000});
 const run=await (await page.request.get('/api/backtests/'+page.url().split('/').at(-1))).json();
 expect(run.provenance.signal_to_open_index_offset).toBe(1);expect(run.config.availability_seconds).toBe(0);
 await page.goto('/compare');await expect(page.locator('.comparison-choice')).toHaveCount(2);
 await page.locator('.comparison-choice input').nth(0).check();await page.locator('.comparison-choice input').nth(1).check();
 await expect(page.locator('.comparison-table')).toBeVisible();await expect(page.locator('.comparison-table thead th')).toHaveCount(3);
 await expect(page.locator('.comparison-table').getByText('Издержки, USDT')).toBeVisible();
 await page.screenshot({path:image('studio-comparison.png'),fullPage:true});expect(errors).toEqual([]);
});

test('Real candle terminal changes native timeframe, saves layout and works in English light theme',async({page})=>{
 const sourceCatalog=await (await page.request.get('/api/datasets')).json();
 test.skip(!sourceCatalog.some((item:{id:string;status:string})=>item.id==='verified_btc_1h_2025_01'&&item.status==='available'),'Optional verified minute archive is not installed in this source clone.');
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));await enter(page);await page.goto('/market');
 await page.getByTestId('chart-dataset').selectOption('verified_btc_1h_2025_01');await expect(page.getByTestId('candlestick-chart')).toBeVisible();
 await expect(page.locator('.terminal-status')).toContainText('744');
 await page.getByRole('button',{name:'Индикаторы и настройки',exact:true}).click();await expect(page.getByTestId('chart-settings')).toBeVisible();
 await page.getByRole('button',{name:'Сохранить вид',exact:true}).click();await page.reload();
 await expect(page.getByTestId('chart-dataset')).toHaveValue('verified_btc_1h_2025_01');await expect(page.getByTestId('candlestick-chart')).toBeVisible();
 await page.screenshot({path:image('studio-terminal-dark.png'),fullPage:true});
 await page.goto('/settings');await page.getByTestId('locale-switch').click();await page.getByRole('button',{name:'Mineral',exact:true}).click();
 await page.goto('/market');await expect(page.getByRole('heading',{name:'Market under the microscope'})).toBeVisible();await expect(page.getByTestId('candlestick-chart')).toBeVisible();
 await page.screenshot({path:image('studio-terminal-light.png'),fullPage:true});
 await page.setViewportSize({width:390,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
 await page.screenshot({path:image('studio-terminal-mobile.png'),fullPage:true});expect(errors).toEqual([]);
});

test('Disconnected copilot is an explicit offline explanation and never applies an invented strategy',async({page})=>{
 await enter(page);await page.getByTestId('create-ai').click();await expect(page).toHaveURL(/\/builder\//);
 await expect(page.getByTestId('copilot-panel')).toBeVisible();await page.getByTestId('copilot-message').fill('Объясни, как завершить мой пустой граф');
 await page.getByTestId('send-copilot').click();await expect(page.locator('.copilot-messages')).toContainText('Локальное объяснение');
 await expect(page.locator('.react-flow__node')).toHaveCount(0);await expect(page.getByTestId('approve-ai-proposal')).toHaveCount(0);
 await page.screenshot({path:image('studio-copilot-offline.png'),fullPage:true});
});

test('ML configuration launches a bounded real process and displays measured splits and native artifact',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));await enter(page);await page.goto('/ml');
 const sourceCatalog=await (await page.request.get('/api/datasets')).json();
 const expectedSource=sourceCatalog.some((item:{id:string;status:string})=>item.id==='verified_btc_4h'&&item.status==='available')?'verified_btc_4h':'demo_btc_4h';
 await expect(page.getByTestId('ml-dataset')).toHaveValue(expectedSource);await page.getByTestId('ml-train').click();
 await expect(page.locator('.ml-job-head')).toContainText('succeeded',{timeout:90_000});await expect(page.locator('.ml-score-grid')).toContainText('brier');
 await page.getByRole('button',{name:'Разделы и причинность',exact:true}).click();await expect(page.locator('pre.json-block')).toContainText('maximum_label_end');
 await page.getByRole('button',{name:'Артефакт и признаки',exact:true}).click();await expect(page.locator('pre.json-block')).toContainText('strategy_node_executable');
 await page.screenshot({path:image('studio-ml-artifact.png'),fullPage:true});expect(errors).toEqual([]);
});
