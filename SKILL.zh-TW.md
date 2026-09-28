> 此為 `SKILL.md` 的中文對照版，僅供閱讀；skill 實際生效的是英文版 `SKILL.md`。

# LoopForge

一個 loop 設計（DESIGN）教練。它會透過六個階段訪談使用者，針對每個回答依照 rubric
（評分準則）提出批評，並產出一份 spec 加上一份 orchestrator（協調者）操作手冊。它不會
執行迴圈，也不會啟動迴圈——產出（emit）之後，何時放行由人類決定。

**Python：** Windows 用 `py -3`，macOS/Linux 用 `python3`。下面每一條指令兩者皆可。

## Modes（模式）
- **Strict（嚴格，預設）。** 每個階段都必須先被批評並收緊，才能進入下一階段。一個薄弱
  的 goal（目標）會擋住進度——這正是本 skill 的重點所在。
- **Fast（`--fast`）。** 當某個階段的回答已經夠紮實時，一次通過採用；只在階段薄弱時
  才反問。適合有經驗的使用者。

## 正在設計的迴圈長什麼樣子

之後讀取 `RUN.md` 的那個 session 就是 **orchestrator**。每次迭代它會：

1. 執行 `loopforge.py check`——讀取檔案來判斷某個 cap（上限）是否還允許再跑一輪；
2. 派出一個**全新的 builder subagent**（子代理）去做這件事；
3. 自行執行 programmatic（程式化）判準；
4. 為腳本無法衡量的部分，派出一個**全新的 judge subagent**；
5. 把 verdict（判決）附加到 `loop-state.json`，並重新產生 `loop.html`。

orchestrator 從不建置、也從不評判。它唯一的工作就是持有 spec 與 verdict 紀錄——一旦它
開始自己動手建置，gate（關卡）所仰賴的獨立性就沒了。

**這裡的「subagent」指的是你的 runtime 用來取得乾淨 context 的任何方式：** 一個
subagent、一個生成出來的 session，或是一個獨立的 agent process。真正的要求是
builder 與 judge 各自啟動時，看不到對方的推理過程——而不是某個特定的 runtime
功能。同樣地，下面的 `${CLAUDE_SKILL_DIR}` 只是這個 skill 自己所在的目錄；換成
你自己 runtime 的對應寫法即可。

## Workflow（工作流程）

1. 從參數解析目標目錄（預設 `./loop`）。先剝走開頭的 `--fast`（當成 fast
   模式旗標處理，不算目標的一部分）。剩下的部分，如果有的話：如果裡面沒有
   `/` 或 `\`，而且也不是一個現存的路徑，就當成是一句簡介，而不是目標目錄
   ——保留預設的 `./loop` 目標（意圖不清楚就問一次），並把這句簡介原文寫進
   `SPEC.yaml` 的 `meta.description`。否則就當成目標目錄。如果解析出來的目標
   已有 `SPEC.yaml`，視為編輯／續作：這個分支下每次改動一個有 id 的概念
   （判準 id、gate 名稱、council 成員 id）之後，重新產出前先對這個 id 做一次
   grep——改名或改範圍，可能會在 `PLAN.md`／`RUN.md` 的敘述文字裡留下編譯器
   抓不到的過期引用（obs #306）。⚠️ 這條目前靠記憶，還沒有 enforcement
   point；第 4 次再發生的話，就改加一個編譯時的交叉檢查，而不是再加提醒
   文字。
2. 以六個階段進行訪談。只在進入該階段時才載入對應的 rubric：
   - Goal（目標） -> `${CLAUDE_SKILL_DIR}/references/goal-rubric.md`
   - Verification（驗證） -> `${CLAUDE_SKILL_DIR}/references/verification-rubric.md`
   - Council（協作陣容） -> `${CLAUDE_SKILL_DIR}/references/council-rubric.md`
   - Gates/Control（關卡／控制） -> `${CLAUDE_SKILL_DIR}/references/control-rubric.md`
   在 Verification 與 Gates/Control 這兩個階段，還要另外載入
   `${CLAUDE_SKILL_DIR}/references/hard-invariants.md`（整合後的錯題簿），並逐一走過
   適用的段落：每一條適用的 invariant（不變條件）要嘛在 `SPEC.yaml` 中變成一條
   check／rule，要嘛就在 spec 的 `invariants:` 區塊裡寫下一行豁免理由。保持沉默不算
   豁免。
3. 在嚴格模式下的每個階段：先覆述使用者的輸入，用具體的替代方案（用使用者所在領域
   的實例，而不是模糊的警語）依照 rubric 提出批評，然後**收斂成一個推薦答案**，
   用使用者自己的用語寫出來。一個只停在列選項的批評，等於把工作丟回給使用者；
   一個推薦答案則讓使用者有東西可以確認、調整或推翻。取得收緊後的答案，然後才
   前進。不要把多個階段一次批量處理。
   - **自己查清楚事實。** 任何環境本身能回答的事——有哪些檔案存在、一支腳本
     已經在檢查什麼、一個 context source 實際上包含什麼——都要自己用工具讀
     出來並引述回去。只有真正的決策才交給使用者；絕不要為了你自己本來就查得
     到的東西去問使用者。
   - **Exit condition（結束條件）：** 一個階段要算作已經收緊，門檻是一個全新的
     builder subagent 能夠依照這個答案行動，而完全不用再問任何一個問題。真正
     讓你可以前進的是這個門檻，不是使用者一句「聽起來不錯」。
   - 當某個階段本身包含好幾個彼此獨立的決策時（例如 Gates & Control 就帶有
     四個各自獨立的 cap），把它們編號、一次過整輪攤出來，每一個都各自附上
     推薦答案。這是在**同一個階段之內**批量處理——階段與階段之間仍然絕不
     合併，而且一個薄弱的答案照樣會當場被擋下。
4. 保持 reviewer（審閱者）與 judge（評判者）角色分明。`revise_until_clean` 必須把某個
   judge 成員或 `human` 指定為 `verdict_source`——絕不能是 reviewer。
5. 預設 judge = 一個**全新的 same-family（同家族）subagent**（`kind: subagent`、
   `context: fresh`）。gate 真正需要的是全新的 context；換一個不同的供應商只是個選項，
   不是預設值。只有在交付內容的風險與代價高到值得花這筆成本與 egress（資料外流）
   時，才提供外部 judge 這個選擇。
6. 要求所有 cap 齊全：`max_iterations`、每個 gate 各自的 `max_revisions`、
   `no_progress.max_stalled_iterations`，以及一個 budget（預算）cap。編譯器會拒絕
   任何缺少其中一項的 spec。
7. 最後一個 gate 的 `verdict_source` 必須是 `human`。中間的 gate 可以自動化到你想要
   的程度；出貨（ship）那道 gate 沒有商量餘地，編譯器會強制執行。
8. 顯示 ASCII flow 預覽（Stage 5）並取得確認，才能產出。
9. 產出到目標目錄：寫入 `SPEC.yaml`（從
   `${CLAUDE_SKILL_DIR}/templates/SPEC.yaml` 開始）與
   `implementation-notes.md`（來自 `${CLAUDE_SKILL_DIR}/templates/`），然後編譯：
   `py -3 ${CLAUDE_SKILL_DIR}/scripts/loopforge.py compile <target>/SPEC.yaml`
   這會寫出 `loop.resolved.json`、`PLAN.md` 與 `RUN.md`。接著渲染出空白儀表板，
   讓使用者在迴圈開跑之前就能看到它：
   `py -3 ${CLAUDE_SKILL_DIR}/scripts/loopforge.py render <target>`
10. 顯示預覽然後停下來。告訴使用者這個迴圈只是設計完成，還沒有啟動；只有在使用者
    表示放行之後，iteration 1（第一次迭代）才會開始，從那一刻起這個 session 就以
    orchestrator 的身分依照 `RUN.md` 行事。LoopForge 的工作到此結束。

## 六個階段
1. **Goal（目標）** — 產出物（outcome artifact）、scope（範圍）、context sources
   （情境來源）、definition_of_done（完成定義）。
2. **Verification（驗證）** — 有型別的判準；優先推向 `programmatic`；若全部都是
   vibe（憑感覺）判準就發出警告。
3. **Council（協作陣容）** — builder subagent（用哪個模型、多少 effort）、
   reviewer（給註記）對比 judge（給 verdict）；預設 judge = 全新的 same-family
   subagent；範圍要小。
4. **Gates & control（關卡與控制）** — plan／delivery／final 這三種 gate，
   revision／iteration／no-progress／budget 這幾種 cap，人類 checkpoint（檢查點），
   isolation（隔離範圍）與副作用。
5. **Preview（預覽）** — ASCII flow；確認。
6. **Emit（產出）** — 寫出 `SPEC.yaml`、編譯、渲染，把放行的決定交給使用者。

## 這些檔案，以及為什麼這樣命名
| 檔案 | 代表意義 | 由誰寫入 |
|---|---|---|
| `SPEC.yaml` | 要建置什麼，以及會如何被評判 | 人類，透過這場訪談 |
| `PLAN.md` | 為什麼這個迴圈會長成這個樣子 | 編譯器 |
| `RUN.md` | 如何執行它（orchestrator 操作手冊） | 編譯器 |
| `implementation-notes.md` | 建置過程中實際發生了什麼 | builder，每次迭代 |
| `loop.resolved.json` | 機器可讀的 spec | 編譯器 |
| `loop-state.json` | 迭代次數、verdict、花費 | orchestrator，每次迭代 |
| `loop.html` | 人類會打開的那個頁面 | `render`，每次迭代 |

Agent 負責編輯 markdown 與 JSON。人類負責閱讀渲染後的 HTML。`loop.html` 是重新產生
出來的，永遠不要手動編輯。

## implementation-notes.md ——builder 的四個段落
**設計決策**（在 spec 保持沉默之處所做的選擇）・**偏離情況**（刻意的偏離，並附上理由）
・**價值取捨**（考慮過的其他方案，以及為什麼是這個方案勝出）・**開放式問題**
（只寫符合以下兩個條件的問題：(1) 兩位稱職的 builder 會做出不同選擇；(2) 這個
選擇會改變 owner 看到的東西或要付出的代價——輸出形狀、scope、cost、可接受的
風險。其餘一律歸類為設計決策——採用你自己的預設值）。

有三個機制掛在這上面：
- **Delivery gate（交付關卡）。** notes 沒有更新 = 什麼都沒交付。在跑任何 gate 之前，
  先把它退回去。
- **Judge input（judge 的輸入）。** judge 會對照 `SPEC.yaml` 讀「偏離情況」。一個沒有
  被記錄下來的偏離本身就是一個 blocking issue（阻擋性問題）；一個有被記錄下來的偏離，
  則是依照它給出的理由來評判。
- **Checkpoint agenda（檢查點議程）。** 在每個人類 checkpoint，orchestrator 會把
  「開放式問題」以及具有決定性影響的「設計決策」呈現出來。人類裁定的結果會被寫回
  `SPEC.yaml`——spec 就是這樣一路累積出決策軌跡的。在寫 CHECKPOINT.md 之前，先用
  上面的判準逐一檢視候選的「開放式問題」；不符合判準的，改歸入「設計決策」。

## File rules（檔案規則）
- 每個 check 與外部呼叫一律使用 argv 陣列，絕不使用 shell 字串。
- 絕不把 API key／token／密碼寫進任何產出的檔案。
- 保持 `SPEC.yaml` 讓人可讀、有註解。機器讀的是 `loop.resolved.json`。
- 開工要讀的清單按角色分開：orchestrator 讀 `RUN.md`，加上
  `loop.resolved.json` 裡的 criteria／stop／gates 欄位；`SPEC.yaml`／
  `PLAN.md` 的內文，只在某個步驟需要某個 section 時才讀進來。builder 或
  judge subagent 則一開工就讀完整份 pack，並且按路徑引用。

## Design-only boundary（只做設計的邊界，硬性規則）
LoopForge 只負責設計與產出。它不會啟動 iteration 1、不會排程任何東西、也不會管理
子代理。它的工作在產出（emitting）那一刻就結束；何時開啟這個迴圈由人類決定。

## Compiler invariants（編譯器已強制執行的不變條件——直接倚賴即可，不必再解釋一次）
- 拒絕 `verdict_source` 不是 `human` 的 final gate。
- 拒絕把 reviewer 當作 `revise_until_clean` 的 verdict_source。
- 拒絕讓 builder 坐在一個為自己成果打分的 gate 上。
- 拒絕任何名字不在 `plan_gate` / `delivery_gate` / `final_gate` 之外的 gate——
  gate 是一個封閉集合，第四個 gate 不會被任何機制強制執行。
- 在任何 policy 之下，拒絕一個沒有指名任何 council 成員的 `verdict_source`；
  `revise_until_clean` 還額外要求那個成員必須是 judge。
- 拒絕 `max_revisions` 超過 no-progress 觀察窗的 `fixed_passes` gate（這樣的 gate
  會在能夠前進之前就先卡死）。
- 拒絕缺少任何必要 cap 的 spec。
- 把 `no_progress.signature_match` 設為 `normalized`。

## Appendix（附錄）—— external runner 模式（無人值守運行）
orchestrator 是一個 session，所以 session 結束時迴圈就會暫停。當迴圈需要撐過這種情況
時——例如過夜運行、排程喚醒、可安全重啟的重試——就把 `execution.mode` 設為
`external_runner`，並在 `execution.runner` 指名你選用的排程器或執行器。`RUN.md` 屆時
會多一個交接段落：執行器讀取 `loop.resolved.json`，並且必須遵守同樣的合約，
**包含人類擔任的 final gate**。持久性只會改變是誰在推動這個迴圈，不會改變是誰在
簽核放行。

## Appendix（附錄）—— external（跨家族）judge
選用項目。一個全新的 same-family subagent 已經能排除 context 汙染；換一個不同的
model family（模型家族）則能額外涵蓋 same-family 的盲點，代價是金錢與一道供應商
邊界。要使用它，在 council 裡加一個成員並設定 `judge: deepseek`（內附
`adapters/judge_deepseek.py`，需要 `DEEPSEEK_API_KEY`），或是自訂一個 `invoke` argv。
唯有在那之後，privacy（隱私）合約才會生效：在 `privacy.egress` 中宣告有什麼會離開
這台機器、設定 redaction（遮蔽）用的 glob 樣式、把 secret（機密）樣式從產出物的
「內容」本身（而不只是檔名）中清乾淨，並且在第一次傳送之前取得明確同意。
