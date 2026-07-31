> 此為 `council-rubric.md` 的中文對照版，僅供閱讀參考；skill 實際載入與生效的是英文版原始檔案。

# Council Rubric（協作陣容評分準則，Stage 3）—— builder、reviewer、judge

orchestrator（協調者，也就是執行 `RUN.md` 的那個 session）不在 council 裡。它只負責
派工、記錄、以及喊停。以下這些角色全部都是它派出去的 subagent（子代理）。

## Roles（角色，要保持分明）
`builder`（建置者） —— 負責做事。每次迭代都是全新的 context（脈絡）。至少要有一個。
`reviewer`（審閱者） —— 只給註記。能提升品質，但**不能**宣告某個 gate 乾淨過關。
`judge`（評判者） —— 給出結構化的 verdict（判決）。唯一能被當作 gate 的
  `verdict_source` 使用的角色。

編譯器強制規定：`verdict_policy: revise_until_clean` 要求 `verdict_source` 必須是
某個 judge 成員或 `human`；builder 完全不能出現在任何 gate 上。一個只有 reviewer
的 gate 可以用 `fixed_passes`，但不能誠實地宣稱自己「乾淨過關」。

## 選擇 builder subagent
問清楚以下幾點，並把答案寫進 spec：
- **用哪個模型？** `inherit`（跟 orchestrator 一樣）是老實的預設值。當工作很機械化
  且規格已經寫得非常完整時，可以指名一個較便宜的模型；當這次迭代牽涉到設計判斷
  或棘手的除錯時，就指名一個更強的模型。
- **要給多少 effort（心力）／多長的繩子（leash）？** 一個拿到緊湊 spec、只需要
  產出一件產出物的 builder，所需要的 effort 會比一個被要求去探索的 builder 少。
- **它的簡報（brief）裡要放什麼？** 只放 goal（目標）、definition of done、它會
  被拿來評判的判準、產出物路徑，以及上一次 verdict 的 blocking issues（阻擋性
  問題）——僅此而已。orchestrator 自己額外加的評論，只會污染下一次嘗試。
- **每次迭代永遠都是全新的 context。** 一個記得自己上三次被拒絕過的 builder，
  會開始為那些被拒絕的東西辯護，而不是去修正它們。

## Judge selection（選 judge）
**預設：一個全新的 same-family（同家族）subagent**（`kind: subagent`、
`context: fresh`）。一個 gate 真正需要的就是全新的 context——judge 看不到
builder 的推理過程，所以它評判的是產出物本身，而不是產出物背後的意圖。這個做法
免費、快速，而且不會離開這個 session。

**選用項目：external／cross-family（外部／跨家族）judge。** 換一個不同的
model family（模型家族）也能涵蓋 same-family 的盲點，代價是金錢與一道供應商
邊界。當共同誤讀的代價會很昂貴時就值得這麼做：公開發布的內容、不可逆的行動，
或任何一次錯誤的「乾淨過關」都很昂貴的情況。用 `judge: deepseek`（內附 adapter）
或自訂的 `invoke` argv 來設定。

不管選哪一種，都要記得 verification rubric 裡的 compensation principle
（補償原則）：judge 的獨立性越弱，就需要越多判準改用 programmatic 來做。

## 寫一份穩定的 judge rubric
- 指名產出物，以及正在被評判的確切判準 ID。
- 要求 judge 給出 blocking_issues，而不是籠統的評論。
- 要求 judge 遵守 JSON verdict 的格式（見 verification rubric）。
- 把包裝文字寫得簡短，讓產出物本身主導 judge 的 context。
- 附上 `implementation-notes.md` 裡的「偏離情況」段落，並指示 judge 把交付內容
  對照 `SPEC.yaml` 來比較：一個沒有被記錄下來的偏離就是一個 blocking issue。

## Privacy（隱私）——只有在 judge 是外部時才適用
一個 same-family subagent 什麼都不會送到任何地方，所以不需要寫 egress（外流）
合約。唯有在你加入一個外部 judge 時：要指名目的地、界定它會收到什麼（`sends`）、
套用 redaction（遮蔽）用的 glob 樣式、把 secret（機密）樣式從產出物的內容本身
（而不只是檔名）中清乾淨，並且在第一次傳送之前要求取得同意。一個本機 judge
會被標記為 no-egress（不會外流）。
