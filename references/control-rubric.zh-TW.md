> 此為 `control-rubric.md` 的中文對照版，僅供閱讀參考；skill 實際載入與生效的是英文版原始檔案。

# Control Rubric（控制評分準則，Stage 4）—— gate、cap、停止條件、邊界

## 必要的 cap（編譯器會拒絕缺少任何一項的 spec）
- `loop_control.max_iterations`
- `gates.*.max_revisions` —— 而且 `gates.*` 恰好就是三個 gate：`plan_gate`、
  `delivery_gate`、`final_gate`。這是一個封閉集合。不要在訪談過程中設計第四個
  gate，也不要幫其中一個改名：編譯器會在 Emit 階段拒絕它，而且一個用其他名字
  存在的 gate，反正也不會被任何機制執行或驗證。更多層次的審查要放進這三個
  gate**裡面**，變成額外的判準或額外的成員。
- `loop_control.no_progress.max_stalled_iterations`
- 至少一個 budget（預算）cap：`wall_clock_min` / `usd` / `tokens`
- 一條描述**成功**的停止條件。
- 一條描述**no-progress（無進展）／重複失敗**的停止條件。

cap 是靠讀取檔案來強制執行的，不是靠記憶。orchestrator 在每次迭代一開始都會執行
`loopforge.py check <dir>`：exit 0 = 可以繼續，非 0 = 停下來並上報。一個要靠迴圈
自己記住的 cap，到了第 6 次迭代就會被忘掉。

## Gate design（關卡設計）
- Plan gate（計畫關卡）要在任何交付工作被花在一份錯誤的計畫上之前先執行。
- Delivery gate（交付關卡）在每個交付產出物之後執行。
- programmatic 檢查要在 judge 呼叫**之前**執行（先做便宜又具決定性的事——把一次
  judge 呼叫花在一個腳本早就能回答的問題上，是雙重浪費：一次浪費在金錢上，
  一次浪費在它觸發的 revision 上）。
- **final gate 永遠是人類。** 中間的 gate 可以完全自動化；出貨（ship）那道 gate
  沒有商量餘地，編譯器會拒絕任何其他的 `verdict_source`。它要防止的失敗很具體：
  builder 誤讀了 spec、一個 same-family judge 用同樣的方式誤讀了它、迴圈自己
  認證自己乾淨過關，然後在成果送出去之前沒有任何人看過。
- 其他的人類 checkpoint 要放在高槓桿的位置：計畫核准之後，或是第一個不可逆行動
  之前。
- 在 gate 的邊界處恢復（resume）執行。

## Delivery contract（交付合約，為什麼一個 gate 可以拒絕執行）
builder 的交付，只有在 `implementation-notes.md` 也一併更新時才算是交付。
沒有更新 = 什麼都沒交付：把它退回去，不要把一個 gate 浪費在它身上。這些 notes
是唯一記錄下 builder 在 spec 沒說的地方做了什麼決定的地方，而 judge 也需要
「偏離情況」才有辦法評判任何偏離。

## Judge-call hygiene（judge 呼叫的衛生守則）
- 一次 judge CLI／adapter 出錯只是一次糟糕的呼叫，絕不能讓整個迴圈當掉。
- 一個帶有 `warning`（adapter 出錯／輸入亂碼／verdict 自相矛盾／輸出無法解析）的
  verdict，是一次**糟糕的 judge 呼叫（BAD JUDGE CALL）**，不是一個真正的
  verdict：它**不會**算進 `max_revisions`，會被另外記錄，而且**絕不會**觸發
  builder 的 revision。處理方式 = 重試 judge 一次，然後上報給人類。
- 同一個 gate 出現 2 次以上的糟糕 judge 呼叫 -> 交給人類 checkpoint，不要再重試。
- Revision 額度是依照**故障來源（FAULT SOURCE）**來計算的。`max_revisions` 只算
  EXECUTOR（執行者）的故障。人類 checkpoint 造成的重做，會開啟一個**新的**迭代，
  絕不會消耗 gate 的額度。（在一次已記錄的執行中，人類自己給的品味意見就消耗掉了
  revision 2/3 與 3/3——原本要留給 builder 故障用的額度，被 builder 完全沒有
  造成的幾輪耗光了。）
- judge 與傳輸層的故障是免費的重新查詢，但受限於另一個獨立的 judge-fault cap
  （大約 3 次），超過就上報給人類。

## No-progress detection（無進展偵測）
- 特徵值是**正規化過**的（轉小寫＋壓縮空白），這樣即使 judge 換個說法重複同樣的
  抱怨，還是會算進 stall（停滯）觀察窗裡。
- `fixed_passes` 的 max_revisions 必須小於等於 no-progress 觀察窗，否則這個 gate
  會在每一輪都附加一次固定失敗，並在能夠前進之前就先卡死。編譯器會**拒絕**
  這種設定。

## Orchestrator handover（協調者交接）
一個已經讀過同一份產出物六次 revision 的 orchestrator，會開始附和它一直在讀的
那個 builder。設定 `orchestrator_handover_every`（預設 3），每隔這麼多次迭代就
把迴圈交給一個全新的 session，或是在 verdict 開始重複的那一刻立刻交接。所有的
狀態都放在檔案裡，就是為了讓 orchestrator 可以被替換：`SPEC.yaml`、`PLAN.md`、
`RUN.md`、`loop-state.json`、`implementation-notes.md` 合起來就是一次完整的交接。

## Human checkpoint agenda（人類檢查點議程）
每一次 checkpoint，都要把以下這些攤在人類面前：每一條「開放式問題」條目、改變了
交付物形狀的「設計決策」，以及任何一個被 judge 放行過關的「偏離情況」。人類裁定
的結果會被寫回 `SPEC.yaml` 並重新編譯——一個回答過一次的問題永遠不會被重新
爭論，下一個 builder 會把這個答案當作一項要求繼承下去。

## Execution boundary（執行邊界）
- 指名迴圈可以修改檔案的範圍：current_workspace（目前工作區）／branch（分支）／
  worktree／sandbox（沙盒）。
- 指認會產生副作用的行動：push、PR 留言、發文、部署、刪除、DB 寫入、外部傳送。
  在**設計時**就決定哪些是 `execute`（執行）、哪些是 `report_only`（僅回報）——
  絕不能交給模型在每次迭代時臨場判斷。
- orchestrator 是一個 session：session 結束時迴圈就會暫停。如果迴圈需要撐過這種
  情況（排程喚醒、可安全重啟的重試），就把 `execution.mode` 設為
  `external_runner`，並指名你選用的執行器。持久性只會改變是誰在推動這個迴圈，
  不會改變是誰在簽核放行。

## Anti-patterns（反面模式，要擋下來）
- 沒有 max iteration count（最大迭代次數）。一個 judge gate 卻沒有 judge。
  budget 只寫在文字敘述裡。
- 沒有 no-progress 偵測器。要求人類簽核卻沒有設 checkpoint。
- 停止條件要求主觀的自我滿足感。
- 一個除了人類以外的角色也能通過的 final gate。
