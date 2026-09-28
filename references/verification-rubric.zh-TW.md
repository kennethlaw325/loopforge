> 此為 `verification-rubric.md` 的中文對照版，僅供閱讀參考；skill 實際載入與生效的是英文版原始檔案。

# Verification Rubric（驗證評分準則，Stage 2）—— 最重要的一個階段

把 definition_of_done（完成定義）轉成有型別、可檢查的判準。優先順序：
programmatic（程式化） > judge（評判） > human（人類）。

## Taxonomy（分類）
`programmatic` —— 一條 argv 指令回傳 pass/fail。具決定性、免費、可重複執行。
  需要 `check`（argv 陣列）加上 `expect`（exit_zero | exit_nonzero |
  stdout_contains）。適用於：計數、schema、必要的標題、build、lint、快照比對、
  URL 是否存活。
`judge` —— 由一個模型依照 `rubric` 打分，回傳一份結構化的 verdict（判決）。
  只用在程式碼無法便宜檢查的語意品質上。rubric 必須具體到讓一個**不同的**
  context（脈絡）也能一致地套用它。
`human` —— 由一個人透過 `prompt` 來簽核。
  用在品味、商業判斷、私有知識、法律風險這幾種情況。

## Compensation principle（補償原則，寫任何 judge 判準之前先讀這段）

**judge 越不獨立，就需要越多驗證改用 programmatic 來做。** judge 的好壞完全
取決於它與 builder 之間的距離，而這個距離分成幾個層級：

| judge | 獨立性 | 帶來什麼好處 |
|---|---|---|
| 同一個 session／同一個 context | 沒有 | 它只會同意自己已經寫過的東西 |
| 全新的 same-family（同家族）subagent（預設） | context 沒有被污染 | 抓得到 drift（偏移），但抓不到共同盲點 |
| 不同的 model family（模型家族，選用） | 沒有 context、也沒有家族盲點 | 要花錢，並跨越一道供應商邊界 |

預設的 judge 是一個全新的 same-family subagent。它看不到 builder 的推理過程，
但它可能跟 builder 共享同樣的盲點——兩者可能會用同一種方式誤讀同一句模稜兩可
的 spec 文字。**要用決定性的方式來補償：任何能寫成 assert、test、schema check
或 grep 的東西，都必須寫成那樣。judge 只裁決那些真正無法被量測的部分。**

寫每一條 judge 判準之前，有個實用的檢驗方法：「一支 20 行的腳本能不能決定這件
事？」如果可以，那它就不該是 judge 判準。計數、是否存在、格式、順序、資料是否
新鮮、是否存活、參照完整性、「沒有 placeholder 文字」——這些全部都是腳本能做的
事，不是判斷。

真正應該留給 judge 的殘餘部分是：這個論點是否連貫、語氣對不對、這個步驟是否真的
能被一個還不知道答案的人照著做下去、這是不是使用者原本要求的那個東西。

## Strict-mode rules（嚴格模式規則）
- 盡可能把判準轉成 `programmatic`。對每一條本來能用腳本檢查、卻寫成 judge／
  human 的判準都要反問回去。
- 每一個帶有 fixture／demo／sample（範例）模式的 `context_source`，都必須有一條
  第 0 步的 programmatic 新鮮度斷言：檢查是否為 real（正式）模式旗標、以及最大
  資料年齡。一個靜默的 fixture no-op（空跑）看起來會跟成功一模一樣——在一次
  已記錄的執行中，一個 fixture 旗標讓一週前的舊資料通過了兩道 gate，直到人類
  checkpoint 才被抓到。
- 如果所有判準都是 judge／human（「全憑感覺的迴圈」），要發出**大聲警告**：
  除非使用者明確接受這個風險，否則要求至少加入一條決定性的檢查。
- 每一條判準只檢查**一件事**，並說明失敗代表什麼。
- judge 的 rubric 必須可以只憑 judge 收到的產出物本身就觀察得到——不能有隱藏
  的 context。
- 絕不能讓 builder 為自己的成果打分；judge 必須是一個獨立、全新的 context，
  編譯器會拒絕讓 builder 坐在某個 gate 上。

## Anti-patterns（反面模式，要擋下來）
- 明明已經有 test 或 schema check 可以做，卻寫成 judge／human 判準。
- 「沒有丟出錯誤」當作唯一的成功判準。
- 「高品質」／「全面」卻沒有指名任何具體面向。
- programmatic 的 `check` 寫成 shell 字串，而不是 argv 陣列。

## Structured judge verdict（結構化的 judge 判決，每個 judge 都必須遵守的合約）
```json
{ "verdict": "pass" | "revise", "blocking_issues": ["[criterion] ..."],
  "confidence": 0.0, "notes": "...",
  "warning": "optional — adapter_error | mojibake_input | verdict_inconsistent | unparseable_judge_output",
  "usage": { "prompt_tokens": 0, "completion_tokens": 0 } }
```
- 每一條 blocking issue（阻擋性問題）開頭都要標明 `[它違反的那條判準]`；一個
  無法指出對應判準的問題只能算是建議（advisory）。（曾經有個 judge 抱怨某件
  沒有任何判準要求過的事，結果燒掉了整個 gate 的 revision（修訂）額度。）
- **judge 同時也要拿 spec 對照交付內容。** 它會讀取 `implementation-notes.md`
  裡的「偏離情況」段落：一個偏離了 `SPEC.yaml`、卻**沒有**被記錄下來的情況，
  本身就是一個 blocking issue；一個有被記錄下來的偏離，則是依照它給出的理由
  是否站得住腳來評判。
- 無法解析／出錯／自相矛盾的輸出會帶有一個 `warning`，這是一次**糟糕的 judge
  呼叫（BAD JUDGE CALL）**，不是一個真正的 verdict——它絕不會中止這個迴圈，
  也絕對**不能**觸發 builder 的 revision（詳見 control rubric）。
- **多條款判準要回報涵蓋範圍（coverage），不能只回一個 verdict。** 加一個
  選填欄位 `"clauses_checked": [{"clause": "<id>", "status": "pass" 或
  "fail"}]`；下一個全新的 judge 會收到上一輪的清單，當作涵蓋地圖（coverage
  map）來用（而不是當作可信的 verdict），還有哪些檔案在那之後有變動，並且
  優先檢查未被勾選過的條款。〔三個全新的 judge 各自找到一個先前判過 pass、
  但其實早就存在的漏洞；revision（修訂）額度就在一句一句慢慢發現的過程裡
  用完了〕
