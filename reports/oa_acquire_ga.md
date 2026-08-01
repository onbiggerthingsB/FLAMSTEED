# OA acquisition run — gate GA (OA Plan 2 v2, V1)

**MODE: LIVE.** Real paid responses from The Odds API.

## Call plan + cumulative gate spend

77 discovery calls (one per distinct `(sport_key, requested_instant)`) @ 1 credit + 434 snapshot calls [T-24h, cut; h2h x eu] @ 10 credits = **4417 credits** projected for the whole plan (mechanical, from the plan itself).

- restored from the journal for gate `ga`: 4405 credits
- outstanding when this run started: 80 credits
- cumulative modeled spend after this run: 4485 credits, against `--max-credits` 4800
- actual billed THIS run (billing headers): 80 credits

The T_issue-cut snapshot is requested at **08:29:00Z** on the venue-LOCAL matchday: the cut is 09:00Z minus a 30-minute buffer and the admissibility rule is a STRICT `<`, so a snapshot returned stamped exactly 08:30:00Z is inadmissible. Requested and returned instants are reported separately below — what we asked for is a decision, what came back is evidence.

| fixture | pool | matchday | kickoff (UTC) | event | requested cut | returned cut | Pinnacle | admissible | notes |
|---|---|---|---|---|---|---|---|---|---|
| United States v Wales | wc2022 | 2022-11-21 | 2022-11-21T19:00:00Z | y | 2022-11-21T08:29:00Z | 2022-11-21T08:25:38Z | y | y | - |
| Senegal v Netherlands | wc2022 | 2022-11-21 | 2022-11-21T16:00:00Z | y | 2022-11-21T08:29:00Z | 2022-11-21T08:25:38Z | y | y | - |
| England v Iran | wc2022 | 2022-11-21 | 2022-11-21T13:00:00Z | y | 2022-11-21T08:29:00Z | 2022-11-21T08:25:38Z | y | y | - |
| France v Australia | wc2022 | 2022-11-22 | 2022-11-22T19:00:00Z | y | 2022-11-22T08:29:00Z | 2022-11-22T08:25:38Z | y | y | - |
| Denmark v Tunisia | wc2022 | 2022-11-22 | 2022-11-22T13:00:00Z | y | 2022-11-22T08:29:00Z | 2022-11-22T08:25:38Z | y | y | - |
| Argentina v Saudi Arabia | wc2022 | 2022-11-22 | 2022-11-22T10:00:00Z | y | 2022-11-22T08:29:00Z | 2022-11-22T08:25:38Z | y | y | - |
| Mexico v Poland | wc2022 | 2022-11-22 | 2022-11-22T16:00:00Z | y | 2022-11-22T08:29:00Z | 2022-11-22T08:25:38Z | y | y | - |
| Germany v Japan | wc2022 | 2022-11-23 | 2022-11-23T13:00:00Z | y | 2022-11-23T08:29:00Z | 2022-11-23T08:25:38Z | y | y | - |
| Belgium v Canada | wc2022 | 2022-11-23 | 2022-11-23T19:00:00Z | y | 2022-11-23T08:29:00Z | 2022-11-23T08:25:38Z | y | y | - |
| Spain v Costa Rica | wc2022 | 2022-11-23 | 2022-11-23T16:00:00Z | y | 2022-11-23T08:29:00Z | 2022-11-23T08:25:38Z | y | y | - |
| Morocco v Croatia | wc2022 | 2022-11-23 | 2022-11-23T10:00:00Z | y | 2022-11-23T08:29:00Z | 2022-11-23T08:25:38Z | y | y | - |
| Brazil v Serbia | wc2022 | 2022-11-24 | 2022-11-24T19:00:00Z | y | 2022-11-24T08:29:00Z | 2022-11-24T08:25:38Z | y | y | - |
| Switzerland v Cameroon | wc2022 | 2022-11-24 | 2022-11-24T10:00:00Z | y | 2022-11-24T08:29:00Z | 2022-11-24T08:25:38Z | y | y | - |
| Uruguay v South Korea | wc2022 | 2022-11-24 | 2022-11-24T13:00:00Z | y | 2022-11-24T08:29:00Z | 2022-11-24T08:25:38Z | y | y | - |
| Portugal v Ghana | wc2022 | 2022-11-24 | 2022-11-24T16:00:00Z | y | 2022-11-24T08:29:00Z | 2022-11-24T08:25:38Z | y | y | - |
| Wales v Iran | wc2022 | 2022-11-25 | 2022-11-25T10:00:00Z | y | 2022-11-25T08:29:00Z | 2022-11-25T08:25:39Z | y | y | - |
| Netherlands v Ecuador | wc2022 | 2022-11-25 | 2022-11-25T16:00:00Z | y | 2022-11-25T08:29:00Z | 2022-11-25T08:25:39Z | y | y | - |
| Qatar v Senegal | wc2022 | 2022-11-25 | 2022-11-25T13:00:00Z | y | 2022-11-25T08:29:00Z | 2022-11-25T08:25:39Z | y | y | - |
| England v United States | wc2022 | 2022-11-25 | 2022-11-25T19:00:00Z | y | 2022-11-25T08:29:00Z | 2022-11-25T08:25:39Z | y | y | - |
| Argentina v Mexico | wc2022 | 2022-11-26 | 2022-11-26T19:00:00Z | y | 2022-11-26T08:29:00Z | 2022-11-26T08:25:38Z | y | y | - |
| France v Denmark | wc2022 | 2022-11-26 | 2022-11-26T16:00:00Z | y | 2022-11-26T08:29:00Z | 2022-11-26T08:25:38Z | y | y | - |
| Poland v Saudi Arabia | wc2022 | 2022-11-26 | 2022-11-26T13:00:00Z | y | 2022-11-26T08:29:00Z | 2022-11-26T08:25:38Z | y | y | - |
| Tunisia v Australia | wc2022 | 2022-11-26 | 2022-11-26T10:00:00Z | y | 2022-11-26T08:29:00Z | 2022-11-26T08:25:38Z | y | y | - |
| Japan v Costa Rica | wc2022 | 2022-11-27 | 2022-11-27T10:00:00Z | y | 2022-11-27T08:29:00Z | 2022-11-27T08:25:38Z | y | y | - |
| Belgium v Morocco | wc2022 | 2022-11-27 | 2022-11-27T13:00:00Z | y | 2022-11-27T08:29:00Z | 2022-11-27T08:25:38Z | y | y | - |
| Spain v Germany | wc2022 | 2022-11-27 | 2022-11-27T19:00:00Z | y | 2022-11-27T08:29:00Z | 2022-11-27T08:25:38Z | y | y | - |
| Croatia v Canada | wc2022 | 2022-11-27 | 2022-11-27T16:00:00Z | y | 2022-11-27T08:29:00Z | 2022-11-27T08:25:38Z | y | y | - |
| Brazil v Switzerland | wc2022 | 2022-11-28 | 2022-11-28T16:00:00Z | y | 2022-11-28T08:29:00Z | 2022-11-28T08:25:37Z | y | y | - |
| Portugal v Uruguay | wc2022 | 2022-11-28 | 2022-11-28T19:00:00Z | y | 2022-11-28T08:29:00Z | 2022-11-28T08:25:37Z | y | y | - |
| South Korea v Ghana | wc2022 | 2022-11-28 | 2022-11-28T13:00:00Z | y | 2022-11-28T08:29:00Z | 2022-11-28T08:25:37Z | y | y | - |
| Cameroon v Serbia | wc2022 | 2022-11-28 | 2022-11-28T10:00:00Z | y | 2022-11-28T08:29:00Z | 2022-11-28T08:25:37Z | y | y | - |
| Wales v England | wc2022 | 2022-11-29 | 2022-11-29T19:00:00Z | y | 2022-11-29T08:29:00Z | 2022-11-29T08:25:37Z | y | y | - |
| Iran v United States | wc2022 | 2022-11-29 | 2022-11-29T19:00:00Z | y | 2022-11-29T08:29:00Z | 2022-11-29T08:25:37Z | y | y | - |
| Ecuador v Senegal | wc2022 | 2022-11-29 | 2022-11-29T15:00:00Z | y | 2022-11-29T08:29:00Z | 2022-11-29T08:25:37Z | y | y | - |
| Qatar v Netherlands | wc2022 | 2022-11-29 | 2022-11-29T15:00:00Z | y | 2022-11-29T08:29:00Z | 2022-11-29T08:25:37Z | y | y | - |
| Saudi Arabia v Mexico | wc2022 | 2022-11-30 | 2022-11-30T19:00:00Z | y | 2022-11-30T08:29:00Z | 2022-11-30T08:25:38Z | y | y | - |
| Poland v Argentina | wc2022 | 2022-11-30 | 2022-11-30T19:00:00Z | y | 2022-11-30T08:29:00Z | 2022-11-30T08:25:38Z | y | y | - |
| Australia v Denmark | wc2022 | 2022-11-30 | 2022-11-30T15:00:00Z | y | 2022-11-30T08:29:00Z | 2022-11-30T08:25:38Z | y | y | - |
| Tunisia v France | wc2022 | 2022-11-30 | 2022-11-30T15:00:00Z | y | 2022-11-30T08:29:00Z | 2022-11-30T08:25:38Z | y | y | - |
| Croatia v Belgium | wc2022 | 2022-12-01 | 2022-12-01T15:00:00Z | y | 2022-12-01T08:29:00Z | 2022-12-01T08:25:37Z | y | y | - |
| Japan v Spain | wc2022 | 2022-12-01 | 2022-12-01T19:00:00Z | y | 2022-12-01T08:29:00Z | 2022-12-01T08:25:37Z | y | y | - |
| Canada v Morocco | wc2022 | 2022-12-01 | 2022-12-01T15:00:00Z | y | 2022-12-01T08:29:00Z | 2022-12-01T08:25:37Z | y | y | - |
| Costa Rica v Germany | wc2022 | 2022-12-01 | 2022-12-01T19:00:00Z | y | 2022-12-01T08:29:00Z | 2022-12-01T08:25:37Z | y | y | - |
| Cameroon v Brazil | wc2022 | 2022-12-02 | 2022-12-02T19:00:00Z | y | 2022-12-02T08:29:00Z | 2022-12-02T08:25:37Z | y | y | - |
| Serbia v Switzerland | wc2022 | 2022-12-02 | 2022-12-02T19:00:00Z | y | 2022-12-02T08:29:00Z | 2022-12-02T08:25:37Z | y | y | - |
| South Korea v Portugal | wc2022 | 2022-12-02 | 2022-12-02T15:00:00Z | y | 2022-12-02T08:29:00Z | 2022-12-02T08:25:37Z | y | y | - |
| Ghana v Uruguay | wc2022 | 2022-12-02 | 2022-12-02T15:00:00Z | y | 2022-12-02T08:29:00Z | 2022-12-02T08:25:37Z | y | y | - |
| Netherlands v United States | wc2022 | 2022-12-03 | 2022-12-03T15:00:00Z | y | 2022-12-03T08:29:00Z | 2022-12-03T08:25:39Z | y | y | - |
| Argentina v Australia | wc2022 | 2022-12-03 | 2022-12-03T19:00:00Z | y | 2022-12-03T08:29:00Z | 2022-12-03T08:25:39Z | y | y | - |
| England v Senegal | wc2022 | 2022-12-04 | 2022-12-04T19:00:00Z | y | 2022-12-04T08:29:00Z | 2022-12-04T08:25:38Z | y | y | - |
| France v Poland | wc2022 | 2022-12-04 | 2022-12-04T15:00:00Z | y | 2022-12-04T08:29:00Z | 2022-12-04T08:25:38Z | y | y | - |
| Japan v Croatia | wc2022 | 2022-12-05 | 2022-12-05T15:00:00Z | y | 2022-12-05T08:29:00Z | 2022-12-05T08:25:37Z | y | y | - |
| Brazil v South Korea | wc2022 | 2022-12-05 | 2022-12-05T19:00:00Z | y | 2022-12-05T08:29:00Z | 2022-12-05T08:25:37Z | y | y | - |
| Morocco v Spain | wc2022 | 2022-12-06 | 2022-12-06T15:00:00Z | y | 2022-12-06T08:29:00Z | 2022-12-06T08:25:37Z | y | y | - |
| Portugal v Switzerland | wc2022 | 2022-12-06 | 2022-12-06T19:00:00Z | y | 2022-12-06T08:29:00Z | 2022-12-06T08:25:37Z | y | y | - |
| Netherlands v Argentina | wc2022 | 2022-12-09 | 2022-12-09T19:00:00Z | y | 2022-12-09T08:29:00Z | 2022-12-09T08:25:38Z | y | y | - |
| Croatia v Brazil | wc2022 | 2022-12-09 | 2022-12-09T15:00:00Z | y | 2022-12-09T08:29:00Z | 2022-12-09T08:25:38Z | y | y | - |
| Morocco v Portugal | wc2022 | 2022-12-10 | 2022-12-10T15:00:00Z | y | 2022-12-10T08:29:00Z | 2022-12-10T08:25:39Z | y | y | - |
| England v France | wc2022 | 2022-12-10 | 2022-12-10T19:00:00Z | y | 2022-12-10T08:29:00Z | 2022-12-10T08:25:39Z | y | y | - |
| Argentina v Croatia | wc2022 | 2022-12-13 | 2022-12-13T19:00:00Z | y | 2022-12-13T08:29:00Z | 2022-12-13T08:25:38Z | y | y | - |
| France v Morocco | wc2022 | 2022-12-14 | 2022-12-14T19:00:00Z | y | 2022-12-14T08:29:00Z | 2022-12-14T08:25:39Z | y | y | - |
| Croatia v Morocco | wc2022 | 2022-12-17 | 2022-12-17T15:00:00Z | y | 2022-12-17T08:29:00Z | 2022-12-17T08:25:38Z | y | y | - |
| Argentina v France | wc2022 | 2022-12-18 | 2022-12-18T15:00:00Z | y | 2022-12-18T08:29:00Z | 2022-12-18T08:25:38Z | y | y | - |
| Mexico v South Africa | wc2026 | 2026-06-11 | 2026-06-11T19:00:00Z | y | 2026-06-11T08:29:00Z | 2026-06-11T08:25:36Z | y | y | - |
| South Korea v Czech Republic | wc2026 | 2026-06-11 | 2026-06-12T02:00:00Z | y | 2026-06-11T08:29:00Z | 2026-06-11T08:25:36Z | y | y | - |
| United States v Paraguay | wc2026 | 2026-06-12 | 2026-06-13T01:00:00Z | y | 2026-06-12T08:29:00Z | 2026-06-12T08:25:36Z | y | y | - |
| Canada v Bosnia and Herzegovina | wc2026 | 2026-06-12 | 2026-06-12T19:00:00Z | y | 2026-06-12T08:29:00Z | 2026-06-12T08:25:36Z | y | y | - |
| Qatar v Switzerland | wc2026 | 2026-06-13 | 2026-06-13T19:00:00Z | y | 2026-06-13T08:29:00Z | 2026-06-13T08:25:36Z | y | y | - |
| Brazil v Morocco | wc2026 | 2026-06-13 | 2026-06-13T22:00:00Z | y | 2026-06-13T08:29:00Z | 2026-06-13T08:25:36Z | y | y | - |
| Haiti v Scotland | wc2026 | 2026-06-13 | 2026-06-14T01:00:00Z | y | 2026-06-13T08:29:00Z | 2026-06-13T08:25:36Z | y | y | - |
| Australia v Turkey | wc2026 | 2026-06-13 | 2026-06-14T04:00:00Z | y | 2026-06-13T08:29:00Z | 2026-06-13T08:25:36Z | y | y | - |
| Germany v Curaçao | wc2026 | 2026-06-14 | 2026-06-14T17:00:00Z | y | 2026-06-14T08:29:00Z | 2026-06-14T08:25:36Z | y | y | - |
| Netherlands v Japan | wc2026 | 2026-06-14 | 2026-06-14T20:00:00Z | y | 2026-06-14T08:29:00Z | 2026-06-14T08:25:36Z | y | y | - |
| Sweden v Tunisia | wc2026 | 2026-06-14 | 2026-06-15T02:00:00Z | y | 2026-06-14T08:29:00Z | 2026-06-14T08:25:36Z | y | y | - |
| Ivory Coast v Ecuador | wc2026 | 2026-06-14 | 2026-06-14T23:00:00Z | y | 2026-06-14T08:29:00Z | 2026-06-14T08:25:36Z | y | y | - |
| Spain v Cape Verde | wc2026 | 2026-06-15 | 2026-06-15T16:00:00Z | y | 2026-06-15T08:29:00Z | 2026-06-15T08:25:37Z | y | y | - |
| Belgium v Egypt | wc2026 | 2026-06-15 | 2026-06-15T19:00:00Z | y | 2026-06-15T08:29:00Z | 2026-06-15T08:25:37Z | y | y | - |
| Saudi Arabia v Uruguay | wc2026 | 2026-06-15 | 2026-06-15T22:00:00Z | y | 2026-06-15T08:29:00Z | 2026-06-15T08:25:37Z | y | y | - |
| Iran v New Zealand | wc2026 | 2026-06-15 | 2026-06-16T01:00:00Z | y | 2026-06-15T08:29:00Z | 2026-06-15T08:25:37Z | y | y | - |
| Iraq v Norway | wc2026 | 2026-06-16 | 2026-06-16T22:00:00Z | y | 2026-06-16T08:29:00Z | 2026-06-16T08:25:37Z | y | y | - |
| Austria v Jordan | wc2026 | 2026-06-16 | 2026-06-17T04:00:00Z | y | 2026-06-16T08:29:00Z | 2026-06-16T08:25:37Z | y | y | - |
| France v Senegal | wc2026 | 2026-06-16 | 2026-06-16T19:00:00Z | y | 2026-06-16T08:29:00Z | 2026-06-16T08:25:37Z | y | y | - |
| Argentina v Algeria | wc2026 | 2026-06-16 | 2026-06-17T01:00:00Z | y | 2026-06-16T08:29:00Z | 2026-06-16T08:25:37Z | y | y | - |
| England v Croatia | wc2026 | 2026-06-17 | 2026-06-17T20:00:00Z | y | 2026-06-17T08:29:00Z | 2026-06-17T08:25:36Z | y | y | - |
| Portugal v DR Congo | wc2026 | 2026-06-17 | 2026-06-17T17:00:00Z | y | 2026-06-17T08:29:00Z | 2026-06-17T08:25:36Z | y | y | - |
| Ghana v Panama | wc2026 | 2026-06-17 | 2026-06-17T23:00:00Z | y | 2026-06-17T08:29:00Z | 2026-06-17T08:25:36Z | y | y | - |
| Uzbekistan v Colombia | wc2026 | 2026-06-17 | 2026-06-18T02:00:00Z | y | 2026-06-17T08:29:00Z | 2026-06-17T08:25:36Z | y | y | - |
| Switzerland v Bosnia and Herzegovina | wc2026 | 2026-06-18 | 2026-06-18T19:00:00Z | y | 2026-06-18T08:29:00Z | 2026-06-18T08:25:36Z | y | y | - |
| Czech Republic v South Africa | wc2026 | 2026-06-18 | 2026-06-18T16:00:00Z | y | 2026-06-18T08:29:00Z | 2026-06-18T08:25:36Z | y | y | - |
| Mexico v South Korea | wc2026 | 2026-06-18 | 2026-06-19T01:00:00Z | y | 2026-06-18T08:29:00Z | 2026-06-18T08:25:36Z | y | y | - |
| Canada v Qatar | wc2026 | 2026-06-18 | 2026-06-18T22:00:00Z | y | 2026-06-18T08:29:00Z | 2026-06-18T08:25:36Z | y | y | - |
| Scotland v Morocco | wc2026 | 2026-06-19 | 2026-06-19T22:00:00Z | y | 2026-06-19T08:29:00Z | 2026-06-19T08:25:36Z | y | y | - |
| Turkey v Paraguay | wc2026 | 2026-06-19 | 2026-06-20T03:00:00Z | y | 2026-06-19T08:29:00Z | 2026-06-19T08:25:36Z | y | y | - |
| United States v Australia | wc2026 | 2026-06-19 | 2026-06-19T19:00:00Z | y | 2026-06-19T08:29:00Z | 2026-06-19T08:25:36Z | y | y | - |
| Brazil v Haiti | wc2026 | 2026-06-19 | 2026-06-20T00:30:00Z | y | 2026-06-19T08:29:00Z | 2026-06-19T08:25:36Z | y | y | - |
| Netherlands v Sweden | wc2026 | 2026-06-20 | 2026-06-20T17:00:00Z | y | 2026-06-20T08:29:00Z | 2026-06-20T08:25:36Z | y | y | - |
| Germany v Ivory Coast | wc2026 | 2026-06-20 | 2026-06-20T20:00:00Z | y | 2026-06-20T08:29:00Z | 2026-06-20T08:25:36Z | y | y | - |
| Tunisia v Japan | wc2026 | 2026-06-20 | 2026-06-21T04:00:00Z | y | 2026-06-20T08:29:00Z | 2026-06-20T08:25:36Z | y | y | - |
| Ecuador v Curaçao | wc2026 | 2026-06-20 | 2026-06-21T00:00:00Z | y | 2026-06-20T08:29:00Z | 2026-06-20T08:25:36Z | y | y | - |
| New Zealand v Egypt | wc2026 | 2026-06-21 | 2026-06-22T01:00:00Z | y | 2026-06-21T08:29:00Z | 2026-06-21T08:25:36Z | y | y | - |
| Spain v Saudi Arabia | wc2026 | 2026-06-21 | 2026-06-21T16:00:00Z | y | 2026-06-21T08:29:00Z | 2026-06-21T08:25:36Z | y | y | - |
| Belgium v Iran | wc2026 | 2026-06-21 | 2026-06-21T19:00:00Z | y | 2026-06-21T08:29:00Z | 2026-06-21T08:25:36Z | y | y | - |
| Uruguay v Cape Verde | wc2026 | 2026-06-21 | 2026-06-21T22:00:00Z | y | 2026-06-21T08:29:00Z | 2026-06-21T08:25:36Z | y | y | - |
| Jordan v Algeria | wc2026 | 2026-06-22 | 2026-06-23T03:00:00Z | y | 2026-06-22T08:29:00Z | 2026-06-22T08:25:36Z | y | y | - |
| France v Iraq | wc2026 | 2026-06-22 | 2026-06-22T21:00:00Z | y | 2026-06-22T08:29:00Z | 2026-06-22T08:25:36Z | y | y | - |
| Norway v Senegal | wc2026 | 2026-06-22 | 2026-06-23T00:00:00Z | y | 2026-06-22T08:29:00Z | 2026-06-22T08:25:36Z | y | y | - |
| Argentina v Austria | wc2026 | 2026-06-22 | 2026-06-22T17:00:00Z | y | 2026-06-22T08:29:00Z | 2026-06-22T08:25:36Z | y | y | - |
| Portugal v Uzbekistan | wc2026 | 2026-06-23 | 2026-06-23T17:00:00Z | y | 2026-06-23T08:29:00Z | 2026-06-23T08:25:36Z | y | y | - |
| Panama v Croatia | wc2026 | 2026-06-23 | 2026-06-23T23:00:00Z | y | 2026-06-23T08:29:00Z | 2026-06-23T08:25:36Z | y | y | - |
| England v Ghana | wc2026 | 2026-06-23 | 2026-06-23T20:00:00Z | y | 2026-06-23T08:29:00Z | 2026-06-23T08:25:36Z | y | y | - |
| Colombia v DR Congo | wc2026 | 2026-06-23 | 2026-06-24T02:00:00Z | y | 2026-06-23T08:29:00Z | 2026-06-23T08:25:36Z | y | y | - |
| South Africa v South Korea | wc2026 | 2026-06-24 | 2026-06-25T01:00:00Z | y | 2026-06-24T08:29:00Z | 2026-06-24T08:25:36Z | y | y | - |
| Mexico v Czech Republic | wc2026 | 2026-06-24 | 2026-06-25T01:00:00Z | y | 2026-06-24T08:29:00Z | 2026-06-24T08:25:36Z | y | y | - |
| Bosnia and Herzegovina v Qatar | wc2026 | 2026-06-24 | 2026-06-24T19:00:00Z | y | 2026-06-24T08:29:00Z | 2026-06-24T08:25:36Z | y | y | - |
| Canada v Switzerland | wc2026 | 2026-06-24 | 2026-06-24T19:00:00Z | y | 2026-06-24T08:29:00Z | 2026-06-24T08:25:36Z | y | y | - |
| Scotland v Brazil | wc2026 | 2026-06-24 | 2026-06-24T22:00:00Z | y | 2026-06-24T08:29:00Z | 2026-06-24T08:25:36Z | y | y | - |
| Morocco v Haiti | wc2026 | 2026-06-24 | 2026-06-24T22:00:00Z | y | 2026-06-24T08:29:00Z | 2026-06-24T08:25:36Z | y | y | - |
| Japan v Sweden | wc2026 | 2026-06-25 | 2026-06-25T23:00:00Z | y | 2026-06-25T08:29:00Z | 2026-06-25T08:25:36Z | y | y | - |
| United States v Turkey | wc2026 | 2026-06-25 | 2026-06-26T02:00:00Z | y | 2026-06-25T08:29:00Z | 2026-06-25T08:25:36Z | y | y | - |
| Curaçao v Ivory Coast | wc2026 | 2026-06-25 | 2026-06-25T20:00:00Z | y | 2026-06-25T08:29:00Z | 2026-06-25T08:25:36Z | y | y | - |
| Tunisia v Netherlands | wc2026 | 2026-06-25 | 2026-06-25T23:00:00Z | y | 2026-06-25T08:29:00Z | 2026-06-25T08:25:36Z | y | y | - |
| Paraguay v Australia | wc2026 | 2026-06-25 | 2026-06-26T02:00:00Z | y | 2026-06-25T08:29:00Z | 2026-06-25T08:25:36Z | y | y | - |
| Ecuador v Germany | wc2026 | 2026-06-25 | 2026-06-25T20:00:00Z | y | 2026-06-25T08:29:00Z | 2026-06-25T08:25:36Z | y | y | - |
| Cape Verde v Saudi Arabia | wc2026 | 2026-06-26 | 2026-06-27T00:00:00Z | y | 2026-06-26T08:29:00Z | 2026-06-26T08:25:36Z | y | y | - |
| Uruguay v Spain | wc2026 | 2026-06-26 | 2026-06-27T00:00:00Z | y | 2026-06-26T08:29:00Z | 2026-06-26T08:25:36Z | y | y | - |
| New Zealand v Belgium | wc2026 | 2026-06-26 | 2026-06-27T03:00:00Z | y | 2026-06-26T08:29:00Z | 2026-06-26T08:25:36Z | y | y | - |
| Norway v France | wc2026 | 2026-06-26 | 2026-06-26T19:00:00Z | y | 2026-06-26T08:29:00Z | 2026-06-26T08:25:36Z | y | y | - |
| Senegal v Iraq | wc2026 | 2026-06-26 | 2026-06-26T19:00:00Z | y | 2026-06-26T08:29:00Z | 2026-06-26T08:25:36Z | y | y | - |
| Egypt v Iran | wc2026 | 2026-06-26 | 2026-06-27T03:00:00Z | y | 2026-06-26T08:29:00Z | 2026-06-26T08:25:36Z | y | y | - |
| Algeria v Austria | wc2026 | 2026-06-27 | 2026-06-28T02:00:00Z | y | 2026-06-27T08:29:00Z | 2026-06-27T08:25:37Z | y | y | - |
| Croatia v Ghana | wc2026 | 2026-06-27 | 2026-06-27T21:00:00Z | y | 2026-06-27T08:29:00Z | 2026-06-27T08:25:37Z | y | y | - |
| DR Congo v Uzbekistan | wc2026 | 2026-06-27 | 2026-06-27T23:30:00Z | y | 2026-06-27T08:29:00Z | 2026-06-27T08:25:37Z | y | y | - |
| Colombia v Portugal | wc2026 | 2026-06-27 | 2026-06-27T23:30:00Z | y | 2026-06-27T08:29:00Z | 2026-06-27T08:25:37Z | y | y | ReadTimeout: The read operation timed out |
| Panama v England | wc2026 | 2026-06-27 | 2026-06-27T21:00:00Z | y | 2026-06-27T08:29:00Z | 2026-06-27T08:25:37Z | y | y | - |
| Jordan v Argentina | wc2026 | 2026-06-27 | 2026-06-28T02:00:00Z | y | 2026-06-27T08:29:00Z | 2026-06-27T08:25:37Z | y | y | - |
| South Africa v Canada | wc2026 | 2026-06-28 | 2026-06-28T19:00:00Z | y | 2026-06-28T08:29:00Z | 2026-06-28T08:25:36Z | y | y | - |
| Netherlands v Morocco | wc2026 | 2026-06-29 | 2026-06-30T01:00:00Z | y | 2026-06-29T08:29:00Z | 2026-06-29T08:25:37Z | y | y | - |
| Brazil v Japan | wc2026 | 2026-06-29 | 2026-06-29T17:00:00Z | y | 2026-06-29T08:29:00Z | 2026-06-29T08:25:37Z | y | y | - |
| Germany v Paraguay | wc2026 | 2026-06-29 | 2026-06-29T20:30:00Z | y | 2026-06-29T08:29:00Z | 2026-06-29T08:25:37Z | y | y | - |
| Mexico v Ecuador | wc2026 | 2026-06-30 | 2026-07-01T01:00:00Z | y | 2026-06-30T08:29:00Z | 2026-06-30T08:25:37Z | y | y | - |
| Ivory Coast v Norway | wc2026 | 2026-06-30 | 2026-06-30T17:00:00Z | y | 2026-06-30T08:29:00Z | 2026-06-30T08:25:37Z | y | y | - |
| France v Sweden | wc2026 | 2026-06-30 | 2026-06-30T21:00:00Z | y | 2026-06-30T08:29:00Z | 2026-06-30T08:25:37Z | y | y | - |
| England v DR Congo | wc2026 | 2026-07-01 | 2026-07-01T16:00:00Z | y | 2026-07-01T08:29:00Z | 2026-07-01T08:25:36Z | y | y | - |
| United States v Bosnia and Herzegovina | wc2026 | 2026-07-01 | 2026-07-02T00:00:00Z | y | 2026-07-01T08:29:00Z | 2026-07-01T08:25:36Z | y | y | - |
| Belgium v Senegal | wc2026 | 2026-07-01 | 2026-07-01T20:00:00Z | y | 2026-07-01T08:29:00Z | 2026-07-01T08:25:36Z | y | y | - |
| Switzerland v Algeria | wc2026 | 2026-07-02 | 2026-07-03T03:00:00Z | y | 2026-07-02T08:29:00Z | 2026-07-02T08:25:36Z | y | y | - |
| Spain v Austria | wc2026 | 2026-07-02 | 2026-07-02T19:00:00Z | y | 2026-07-02T08:29:00Z | 2026-07-02T08:25:36Z | y | y | - |
| Portugal v Croatia | wc2026 | 2026-07-02 | 2026-07-02T23:00:00Z | y | 2026-07-02T08:29:00Z | 2026-07-02T08:25:36Z | y | y | - |
| Argentina v Cape Verde | wc2026 | 2026-07-03 | 2026-07-03T22:00:00Z | y | 2026-07-03T08:29:00Z | 2026-07-03T08:25:36Z | y | y | - |
| Australia v Egypt | wc2026 | 2026-07-03 | 2026-07-03T18:00:00Z | y | 2026-07-03T08:29:00Z | 2026-07-03T08:25:36Z | y | y | - |
| Colombia v Ghana | wc2026 | 2026-07-03 | 2026-07-04T01:30:00Z | y | 2026-07-03T08:29:00Z | 2026-07-03T08:25:36Z | y | y | - |
| Paraguay v France | wc2026 | 2026-07-04 | 2026-07-04T21:00:00Z | y | 2026-07-04T08:29:00Z | 2026-07-04T08:25:36Z | y | y | - |
| Canada v Morocco | wc2026 | 2026-07-04 | 2026-07-04T17:00:00Z | y | 2026-07-04T08:29:00Z | 2026-07-04T08:25:36Z | y | y | - |
| Mexico v England | wc2026 | 2026-07-05 | 2026-07-06T00:00:00Z | y | 2026-07-05T08:29:00Z | 2026-07-05T08:25:36Z | y | y | - |
| Brazil v Norway | wc2026 | 2026-07-05 | 2026-07-05T20:00:00Z | y | 2026-07-05T08:29:00Z | 2026-07-05T08:25:36Z | y | y | - |
| United States v Belgium | wc2026 | 2026-07-06 | 2026-07-07T00:00:00Z | y | 2026-07-06T08:29:00Z | 2026-07-06T08:25:36Z | y | y | - |
| Portugal v Spain | wc2026 | 2026-07-06 | 2026-07-06T19:00:00Z | y | 2026-07-06T08:29:00Z | 2026-07-06T08:25:36Z | y | y | - |
| Argentina v Egypt | wc2026 | 2026-07-07 | 2026-07-07T16:00:00Z | y | 2026-07-07T08:29:00Z | 2026-07-07T08:25:36Z | y | y | - |
| Switzerland v Colombia | wc2026 | 2026-07-07 | 2026-07-07T20:00:00Z | y | 2026-07-07T08:29:00Z | 2026-07-07T08:25:36Z | y | y | - |
| France v Morocco | wc2026 | 2026-07-09 | 2026-07-09T20:00:00Z | y | 2026-07-09T08:29:00Z | 2026-07-09T08:25:38Z | y | y | - |
| Spain v Belgium | wc2026 | 2026-07-10 | 2026-07-10T19:00:00Z | y | 2026-07-10T08:29:00Z | 2026-07-10T08:25:37Z | y | y | - |
| Norway v England | wc2026 | 2026-07-11 | 2026-07-11T21:00:00Z | y | 2026-07-11T08:29:00Z | 2026-07-11T08:25:37Z | y | y | - |
| Argentina v Switzerland | wc2026 | 2026-07-11 | 2026-07-12T01:00:00Z | y | 2026-07-11T08:29:00Z | 2026-07-11T08:25:37Z | y | y | - |
| France v Spain | wc2026 | 2026-07-14 | 2026-07-14T19:00:00Z | y | 2026-07-14T08:29:00Z | 2026-07-14T08:25:37Z | y | y | - |
| England v Argentina | wc2026 | 2026-07-15 | 2026-07-15T19:00:00Z | y | 2026-07-15T08:29:00Z | 2026-07-15T08:25:37Z | y | y | - |
| France v England | wc2026 | 2026-07-18 | 2026-07-18T21:00:00Z | y | 2026-07-18T08:29:00Z | 2026-07-18T08:25:37Z | y | y | - |
| Spain v Argentina | wc2026 | 2026-07-19 | 2026-07-19T19:00:00Z | y | 2026-07-19T08:29:00Z | 2026-07-19T08:25:37Z | y | y | - |
| Spain v Croatia | euro2024 | 2024-06-15 | 2024-06-15T16:00:00Z | y | 2024-06-15T08:29:00Z | 2024-06-15T08:25:37Z | y | y | - |
| Hungary v Switzerland | euro2024 | 2024-06-15 | 2024-06-15T13:00:00Z | y | 2024-06-15T08:29:00Z | 2024-06-15T08:25:37Z | y | y | - |
| Italy v Albania | euro2024 | 2024-06-15 | 2024-06-15T19:00:00Z | y | 2024-06-15T08:29:00Z | 2024-06-15T08:25:37Z | y | y | - |
| Poland v Netherlands | euro2024 | 2024-06-16 | 2024-06-16T13:00:00Z | y | 2024-06-16T08:29:00Z | 2024-06-16T08:25:37Z | y | y | - |
| Serbia v England | euro2024 | 2024-06-16 | 2024-06-16T19:00:00Z | y | 2024-06-16T08:29:00Z | 2024-06-16T08:25:37Z | y | y | - |
| Slovenia v Denmark | euro2024 | 2024-06-16 | 2024-06-16T16:00:00Z | y | 2024-06-16T08:29:00Z | 2024-06-16T08:25:37Z | y | y | - |
| Belgium v Slovakia | euro2024 | 2024-06-17 | 2024-06-17T16:00:00Z | y | 2024-06-17T08:29:00Z | 2024-06-17T08:25:37Z | y | y | - |
| Austria v France | euro2024 | 2024-06-17 | 2024-06-17T19:00:00Z | y | 2024-06-17T08:29:00Z | 2024-06-17T08:25:37Z | y | y | - |
| Romania v Ukraine | euro2024 | 2024-06-17 | 2024-06-17T13:00:00Z | y | 2024-06-17T08:29:00Z | 2024-06-17T08:25:37Z | y | y | - |
| Portugal v Czech Republic | euro2024 | 2024-06-18 | 2024-06-18T19:00:00Z | y | 2024-06-18T08:29:00Z | 2024-06-18T08:25:37Z | y | y | - |
| Turkey v Georgia | euro2024 | 2024-06-18 | 2024-06-18T16:00:00Z | y | 2024-06-18T08:29:00Z | 2024-06-18T08:25:37Z | y | y | - |
| Germany v Hungary | euro2024 | 2024-06-19 | 2024-06-19T16:00:00Z | y | 2024-06-19T08:29:00Z | 2024-06-19T08:25:38Z | y | y | - |
| Croatia v Albania | euro2024 | 2024-06-19 | 2024-06-19T13:00:00Z | y | 2024-06-19T08:29:00Z | 2024-06-19T08:25:38Z | y | y | - |
| Scotland v Switzerland | euro2024 | 2024-06-19 | 2024-06-19T19:00:00Z | y | 2024-06-19T08:29:00Z | 2024-06-19T08:25:38Z | y | y | - |
| Denmark v England | euro2024 | 2024-06-20 | 2024-06-20T16:00:00Z | y | 2024-06-20T08:29:00Z | 2024-06-20T08:25:37Z | y | y | - |
| Slovenia v Serbia | euro2024 | 2024-06-20 | 2024-06-20T13:00:00Z | y | 2024-06-20T08:29:00Z | 2024-06-20T08:25:37Z | y | y | - |
| Spain v Italy | euro2024 | 2024-06-20 | 2024-06-20T19:00:00Z | y | 2024-06-20T08:29:00Z | 2024-06-20T08:25:37Z | y | y | - |
| Netherlands v France | euro2024 | 2024-06-21 | 2024-06-21T19:00:00Z | y | 2024-06-21T08:29:00Z | 2024-06-21T08:25:38Z | y | y | - |
| Poland v Austria | euro2024 | 2024-06-21 | 2024-06-21T16:00:00Z | y | 2024-06-21T08:29:00Z | 2024-06-21T08:25:38Z | y | y | - |
| Slovakia v Ukraine | euro2024 | 2024-06-21 | 2024-06-21T13:00:00Z | y | 2024-06-21T08:29:00Z | 2024-06-21T08:25:38Z | y | y | - |
| Georgia v Czech Republic | euro2024 | 2024-06-22 | 2024-06-22T13:00:00Z | y | 2024-06-22T08:29:00Z | 2024-06-22T08:25:37Z | y | y | - |
| Turkey v Portugal | euro2024 | 2024-06-22 | 2024-06-22T16:00:00Z | y | 2024-06-22T08:29:00Z | 2024-06-22T08:25:37Z | y | y | - |
| Belgium v Romania | euro2024 | 2024-06-22 | 2024-06-22T19:00:00Z | y | 2024-06-22T08:29:00Z | 2024-06-22T08:25:37Z | y | y | - |
| Germany v Switzerland | euro2024 | 2024-06-23 | 2024-06-23T19:00:00Z | y | 2024-06-23T08:29:00Z | 2024-06-23T08:25:37Z | y | y | - |
| Scotland v Hungary | euro2024 | 2024-06-23 | 2024-06-23T19:00:00Z | y | 2024-06-23T08:29:00Z | 2024-06-23T08:25:37Z | y | y | - |
| Croatia v Italy | euro2024 | 2024-06-24 | 2024-06-24T19:00:00Z | y | 2024-06-24T08:29:00Z | 2024-06-24T08:25:37Z | y | y | - |
| Albania v Spain | euro2024 | 2024-06-24 | 2024-06-24T19:00:00Z | y | 2024-06-24T08:29:00Z | 2024-06-24T08:25:37Z | y | y | - |
| Denmark v Serbia | euro2024 | 2024-06-25 | 2024-06-25T19:00:00Z | y | 2024-06-25T08:29:00Z | 2024-06-25T08:25:37Z | y | y | - |
| Netherlands v Austria | euro2024 | 2024-06-25 | 2024-06-25T16:00:00Z | y | 2024-06-25T08:29:00Z | 2024-06-25T08:25:37Z | y | y | - |
| France v Poland | euro2024 | 2024-06-25 | 2024-06-25T16:00:00Z | y | 2024-06-25T08:29:00Z | 2024-06-25T08:25:37Z | y | y | - |
| England v Slovenia | euro2024 | 2024-06-25 | 2024-06-25T19:00:00Z | y | 2024-06-25T08:29:00Z | 2024-06-25T08:25:37Z | y | y | - |
| Slovakia v Romania | euro2024 | 2024-06-26 | 2024-06-26T16:00:00Z | y | 2024-06-26T08:29:00Z | 2024-06-26T08:25:38Z | y | y | - |
| Ukraine v Belgium | euro2024 | 2024-06-26 | 2024-06-26T16:00:00Z | y | 2024-06-26T08:29:00Z | 2024-06-26T08:25:38Z | y | y | - |
| Georgia v Portugal | euro2024 | 2024-06-26 | 2024-06-26T19:00:00Z | y | 2024-06-26T08:29:00Z | 2024-06-26T08:25:38Z | y | y | - |
| Czech Republic v Turkey | euro2024 | 2024-06-26 | 2024-06-26T19:00:00Z | y | 2024-06-26T08:29:00Z | 2024-06-26T08:25:38Z | y | y | - |
| Switzerland v Italy | euro2024 | 2024-06-29 | 2024-06-29T16:00:00Z | y | 2024-06-29T08:29:00Z | 2024-06-29T08:25:38Z | y | y | - |
| Germany v Denmark | euro2024 | 2024-06-29 | 2024-06-29T19:00:00Z | y | 2024-06-29T08:29:00Z | 2024-06-29T08:25:38Z | y | y | - |
| Spain v Georgia | euro2024 | 2024-06-30 | 2024-06-30T19:00:00Z | y | 2024-06-30T08:29:00Z | 2024-06-30T08:25:38Z | y | y | - |
| England v Slovakia | euro2024 | 2024-06-30 | 2024-06-30T16:00:00Z | y | 2024-06-30T08:29:00Z | 2024-06-30T08:25:38Z | y | y | - |
| Portugal v Slovenia | euro2024 | 2024-07-01 | 2024-07-01T19:00:00Z | y | 2024-07-01T08:29:00Z | 2024-07-01T08:25:38Z | y | y | - |
| France v Belgium | euro2024 | 2024-07-01 | 2024-07-01T16:00:00Z | y | 2024-07-01T08:29:00Z | 2024-07-01T08:25:38Z | y | y | - |
| Romania v Netherlands | euro2024 | 2024-07-02 | 2024-07-02T16:00:00Z | y | 2024-07-02T08:29:00Z | 2024-07-02T08:25:37Z | y | y | - |
| Austria v Turkey | euro2024 | 2024-07-02 | 2024-07-02T19:00:00Z | y | 2024-07-02T08:29:00Z | 2024-07-02T08:25:37Z | y | y | - |
| Germany v Spain | euro2024 | 2024-07-05 | 2024-07-05T16:00:00Z | y | 2024-07-05T08:29:00Z | 2024-07-05T08:25:37Z | y | y | - |
| Portugal v France | euro2024 | 2024-07-05 | 2024-07-05T19:00:00Z | y | 2024-07-05T08:29:00Z | 2024-07-05T08:25:37Z | y | y | - |
| Netherlands v Turkey | euro2024 | 2024-07-06 | 2024-07-06T19:00:00Z | y | 2024-07-06T08:29:00Z | 2024-07-06T08:25:37Z | y | y | - |
| England v Switzerland | euro2024 | 2024-07-06 | 2024-07-06T16:00:00Z | y | 2024-07-06T08:29:00Z | 2024-07-06T08:25:37Z | y | y | - |
| Spain v France | euro2024 | 2024-07-09 | 2024-07-09T19:00:00Z | y | 2024-07-09T08:29:00Z | 2024-07-09T08:25:37Z | y | y | - |
| Netherlands v England | euro2024 | 2024-07-10 | 2024-07-10T19:00:00Z | y | 2024-07-10T08:29:00Z | 2024-07-10T08:25:37Z | y | y | - |
| Spain v England | euro2024 | 2024-07-14 | 2024-07-14T19:00:00Z | y | 2024-07-14T08:29:00Z | 2024-07-14T08:25:37Z | y | y | - |

Population eligibility (admissible cut quote): **217 / 217** fixtures. Solver success is applied on top of this at V8; the inventory is frozen into the lock there, never here.

## Provenance (full sha256 of the archived raw response)

- 7beaba47d99370d78420a173c394f44cf135f18e: discovery 1ca3d1a08962e696e59b5c0fe34148d0e2ec13274a22ac5da144d4e2cd74f8dc, T-24h 8b42a37c39e6f105e3f6050a365b4f8d35f08b43768778fe7298aa4a89f8afc5, cut 7622078762989efc77f715f51b05098d99584d38b847c63c2c4a8b27b0992768
- 8593af66fd3744540638509ffae695aff3087c9b: discovery 1ca3d1a08962e696e59b5c0fe34148d0e2ec13274a22ac5da144d4e2cd74f8dc, T-24h 5e6d46e6c7903a16670d07839a457beb3dd0f5ba118e4c2e2cc1330a0b55e981, cut 2caa077ccf2063bbefdfe587fc267b987ae63a473f061bab86ce8151c52f20f3
- f7c2a18571c3216a41d60bd8d7bc374aaf219262: discovery 1ca3d1a08962e696e59b5c0fe34148d0e2ec13274a22ac5da144d4e2cd74f8dc, T-24h 38fdf6d0df74829579eb710cc09dbdd494e975867d1c20e2d7f1175a63822152, cut edda65cea244815e24060093745f68821535d02c2b62a395b703f62e53489cbc
- 3b77892e774d2d668797dae732970c6849641f73: discovery a0df7968ed31d2c8e8d8bcdad7032f19dc843ec778026d4cf547c51722b50236, T-24h 395723e36d30bf595ebcd459cf64dffa59fc278463d8139c5610b8788527476f, cut 58ae3249ce24492714b93db0f3cdb6639f8d7288b516ae15d2919c726433d624
- 91b6a0b6d93dc63895985a5b1c3d0f3e4bfa979c: discovery a0df7968ed31d2c8e8d8bcdad7032f19dc843ec778026d4cf547c51722b50236, T-24h e07707991af58aa5f4323fab39363c2194c6ff067a02beb8b88f14f5f9d09199, cut 32d717c2e024bb86100955842673dcfebeb0bbce66f4576796dcd47ad8fbf91d
- 99a5ed7ee0ca59bb4feafcd1fdcaf7cbfacab4d0: discovery a0df7968ed31d2c8e8d8bcdad7032f19dc843ec778026d4cf547c51722b50236, T-24h 4c7656e0758008a30e33c644a282d4c48456711e0bbc5c1337ff97010da4792e, cut 46c2a8883007d264ddac281a67ee061fbaf056ddf17dd1393225c78f8929d692
- c130a0869a654243f4532a45fd707b5671b5d207: discovery a0df7968ed31d2c8e8d8bcdad7032f19dc843ec778026d4cf547c51722b50236, T-24h 67d96c01347b16f8d2729e0d730821e139b7b47703c8be1e3f9c5ecae1e6b49f, cut a245f60ee8a81ba6bc85db06871e5d2d3a745dfdcd7a3924c2104db5efb9367a
- 1acba342a09c0f3d7d88233b98eaead73cde9244: discovery 27bd5f49bab28151117bceccd750924370557b37e7c3edab9e626cc656823e0a, T-24h fd683b15469447fc50c4b50db0ec0b4a0ccea3d7ce64fd4c5b5062f03c927245, cut 013eb8649d924cb16fdcf32cf93b2d63f395256dd2f795719c25799965405bd0
- 790b7b0ed504bc5caef0e4e80f980b70d259a031: discovery 27bd5f49bab28151117bceccd750924370557b37e7c3edab9e626cc656823e0a, T-24h 01b0721f23f4223be9b07e595ee49e87a1cad6ed4f0d4137564be18804df0ba5, cut 6a410e554bdb038d6d3cdb2e0c1274c0449e8777dbbd319c21b53c8e54cc651f
- 9c5abaf39dbc8559a91e986d657ceeea661df799: discovery 27bd5f49bab28151117bceccd750924370557b37e7c3edab9e626cc656823e0a, T-24h bf3dfee923cda5e8c9e96137b3e1069f7e6276deaee816816354feba0dfdbae0, cut 3c874ca3db038cea2cc0d525f956bc0313e3f5840c40873c8586c1155dc5728f
- d42a0b75f5d8595d2be72ddc0e65ba1319b0d8e4: discovery 27bd5f49bab28151117bceccd750924370557b37e7c3edab9e626cc656823e0a, T-24h 0606880491df7ba4487225af87630751e0dfae28a1d6e7f8a6217e49730b8b3b, cut 113d6c3960433b0cc04249b95101f308bcd3f8f8e071a420887e43b121ad0ef1
- 2c5f6f30c7fd8932175ff2161861592146a1d3c5: discovery fa39b0a6f2bc7569f10a760c94e68ec9d23a1d35c0187d1a3da4f5eb4426db5c, T-24h 7a64cc6d5d933eb916caf6dae5781dadd0f9484ea43db0fda9498c3190d62f56, cut 612340c1413d3b2dfd4a06af0a61ee2d9648579f551296ff31fd175d01ea4ed4
- 94cf24a88cbe4fc470d8514f732c242866908a40: discovery fa39b0a6f2bc7569f10a760c94e68ec9d23a1d35c0187d1a3da4f5eb4426db5c, T-24h e806fb6c09cf679a962d0308ce094656cc87d3206939788887fbf4b422d785bb, cut c894b12570cf6d2c1524c93b380268ecf1e71b96ec0980527ff19be22c0ea3e6
- 9680a2964ac3a4e6896ee7977e93e18b0bad10ce: discovery fa39b0a6f2bc7569f10a760c94e68ec9d23a1d35c0187d1a3da4f5eb4426db5c, T-24h eb19863f67777a6bfe2052f6283b1e06b05e2e3eadcecde49374df861513b493, cut 7b05d45c1a164fcda66d9281d09bfc9f82936a10e9426f93e8d7f36065d9fc72
- c91fd31608fc95f899e5b8d7d7d269c75d5dbce7: discovery fa39b0a6f2bc7569f10a760c94e68ec9d23a1d35c0187d1a3da4f5eb4426db5c, T-24h 46bfcb96ea2285fd0e2357decda4446ba751b8f25b9e2e1a5de5a34e36099fc1, cut a0a6d1b749c8ac27623747f63ab3a71df6ffe3aa02bb0f00b4f80be9afa1706d
- 12bcc95c4bf210e0e479a6f974f6e73eb450c385: discovery 2f6e2e3cae1d626e840e6fd8172d3545052b0e791217df8955abe69a96fa38bf, T-24h 0155a44ace136c9d138cd89f5aa168f683ecc2a7d0081e87be770521265803ee, cut ff38a8f226bd1a4498220ac5121eb561a2f731c597d7dd483473ab6375d96655
- 2b4d088e789caac6f14c0c15cc08476c38861c71: discovery 2f6e2e3cae1d626e840e6fd8172d3545052b0e791217df8955abe69a96fa38bf, T-24h 5c896674fbd0f955e354405e58d36180ea0207f2db3617697f53091164fba055, cut 3a583e03155b6d8efad7586085f1d0f8b1c78321873a7d4bef50273a1dd862e1
- 4479ea84262f09600e022c4bcd157334aa7b91e9: discovery 2f6e2e3cae1d626e840e6fd8172d3545052b0e791217df8955abe69a96fa38bf, T-24h 9f9d9945d6b4f67157da453a264193c89209866c766d1a068b3e5d23250730c2, cut 3ba57b81aea4d104f1ed5c4f1d76b0fd09a441380235881faa9f559a0cd882ab
- 489fae03ad3deef682ae4fe59525cf9c2024fb1c: discovery 2f6e2e3cae1d626e840e6fd8172d3545052b0e791217df8955abe69a96fa38bf, T-24h f3c6440a8e93a1306242765d7190e9c5f95f9288e1958634b1cd1bcd3581f5cb, cut 4878029492e436d0764ef5c68eedc9fd5326f019a5d4c4cb2d0e26eef4b80b4b
- 0c49025d02e04d4063b84c6931ff27f38bfb9f44: discovery e850739dbcfed16770df7caff5fed7eadfebf6526a83cb1bdd59ba33cdfaa3cf, T-24h 2466c96cc7eaa87c1c2358815d2fd40f86dcd16c8735459b155fd3bda8382a03, cut f850f97701b81e144ceec2b5b2085dc978f2804fb08c46c1e84b4d7d1fe55b14
- 5994a5c2f53d721f4685829d4790cf2b6d5a9b34: discovery e850739dbcfed16770df7caff5fed7eadfebf6526a83cb1bdd59ba33cdfaa3cf, T-24h 329c8fdf1ce72772a5e78ce3850094f1a3bffec5e219afa7e497a9997b79caa6, cut c01655ceadeaa4ffbfb9dd6667b7586cda5ced7b49960c0106a458e61900d322
- 6d0eee65e441412d7e198ebfe35c2f965fb6eb9a: discovery e850739dbcfed16770df7caff5fed7eadfebf6526a83cb1bdd59ba33cdfaa3cf, T-24h 69e93e8eccd8fbcb32f9a8451b0362359068d57365882bbf7e02d26d158759f9, cut 1a753859b8d7607a4b74c526f96643a38eed1730dcb2ce0115760253a329b7b3
- d47495762f41ca196fda377ce302af0455537d3e: discovery e850739dbcfed16770df7caff5fed7eadfebf6526a83cb1bdd59ba33cdfaa3cf, T-24h 2c98e759a82704b0e96357b239cff76a2fc4224389246c8e1d5424be175f0c7c, cut 01023b52a8db33b56c400535c25586c6713d98e52b5f11c804eff2775af2a128
- 26ad295b18b7061f7ede77e7313a55e43b8d45b9: discovery 9267b85007120f86400f5542de8b4424bd56e1509cc5f76f4774b46b93412c64, T-24h 55f6c2b0a557be79bf35d81f5dc9d7ff4c9e890720cdabb2e4d3b03cdd371675, cut b0973a2f1a4795dd1528ab623d9ee1a28ce0f4c1559c86895c4af9bffeb927d5
- 31cfc3caa9f989561d373b9670dc156a1b102599: discovery 9267b85007120f86400f5542de8b4424bd56e1509cc5f76f4774b46b93412c64, T-24h 4bf36a9849f1b8ecbdbea9a8180a4790881880a99ff76099188736c0ee73b0aa, cut 777f553b07289cd283dbce7106aa71370e41032135b5642354caaa089aba2661
- 770f45f6b01451cd9ac43c348ec4613fa6217574: discovery 9267b85007120f86400f5542de8b4424bd56e1509cc5f76f4774b46b93412c64, T-24h 4606b104714641408c02b7c65d5b9391dee7c3ab2227c8d114c14e9f59abdca0, cut 24fe7498e6c568304fd1d4bac0d17474aa2409a62600b697640b201d0e1cbdaa
- a09bd4e47e354334bddfae50346eea097fdbf8cc: discovery 9267b85007120f86400f5542de8b4424bd56e1509cc5f76f4774b46b93412c64, T-24h 183064ee622eb9333a4556ca372dac2dc497bfc06bb0315551aefeb95ea3e915, cut 612fd379c2f75846eec178afc71fc07ded833cd20ac9f5ef48e8f2ba0400de87
- 7755b47e16289434c1989550389c8ffdedcdcf65: discovery 009f8872bdfdb9c8b91efb949b2c415c6e0cbf2f3eb988484660f5f0ed364a5f, T-24h 7d12ef9b9e965bd21fe728f11b08b990aa2983d2f1963110768c52e742228148, cut b60a8b6b914edb7c2ba426f5abe90e7670f333b90f137569291c257b405d8f67
- 9a04a18679612035226957fb6094ab140db25f49: discovery 009f8872bdfdb9c8b91efb949b2c415c6e0cbf2f3eb988484660f5f0ed364a5f, T-24h f6f4275204fe233434e35faa61ebdcf340a6608fffa6b11d1defc7fdc022c9bc, cut 9b683c236075963f9ce7e5f3aa4490554b9f721b5ced900b4cf32672f8cf71d1
- 9b579d02acb54f98b92e4ce9f0d645e37e310d22: discovery 009f8872bdfdb9c8b91efb949b2c415c6e0cbf2f3eb988484660f5f0ed364a5f, T-24h a4d1445f1db37cbafebe4774f5d040b82313dba18b5f7bdd64bf69c218240b2f, cut 93e1aa0472f5817000c65bbb12fa16736c4ec2c0ecda64d733885b95e3ca92d4
- d718e0cc74d22c47705fc0b855530a28f3b00e55: discovery 009f8872bdfdb9c8b91efb949b2c415c6e0cbf2f3eb988484660f5f0ed364a5f, T-24h 7d3b6ff946c9610d6d075c39f96117d3721c36e28d84fe042e62a3585a4e2ce2, cut 10be089628ec32130ad2111aaef09143d13dc1746e3ae195ba5cf6552d6df452
- 04f673bef56bbabe4ff1ca7d454e8f0dfed74431: discovery e3ab5e70d0d4fb4e0a65e6307d4ff205e321c35d0694ae799b411521adfcd8fc, T-24h 9e10d71df7fa1791fd259ef26fe26c4a786a16b8ed100c60336f9d81b1048322, cut e27a6202cb1748b6813099d098ca9cecc625fd34485b05ca29005a2e2244f6e1
- 407b06fb408913d54d183064aa7e68e04744092d: discovery e3ab5e70d0d4fb4e0a65e6307d4ff205e321c35d0694ae799b411521adfcd8fc, T-24h b6a1a45a1f1e6ac509d498e39f5860979440d02d75c8eda3de99011729ffc329, cut 87820270c9296486cfa5cd413a6000022d0d22913629b35b25c639868fed09a9
- 92bffb03c9063850b5817a7be21697bd601c9d6d: discovery e3ab5e70d0d4fb4e0a65e6307d4ff205e321c35d0694ae799b411521adfcd8fc, T-24h 369c6b165fbdd806bc1187320fd74ce10ca1a52c80a0b815e86be042e472abb2, cut 11e84878572831c700e45bf4160cbdbfc219150c36a2e0b0a975246773a19f85
- 9d062d19b6c11978d6a2c3c9fb0a6fed80e44ac4: discovery e3ab5e70d0d4fb4e0a65e6307d4ff205e321c35d0694ae799b411521adfcd8fc, T-24h 9b80105ab4ccd7c20da3a738c568225c69a126bc8780eca015930cf19be2faf1, cut 384d3ec84fa6c3f70bacba8947e60ed9bac1c8f8814ade64a42047d9f4d11cab
- 860b5dc43722ecabfdfae64a294a60a01bfd590e: discovery a47bba16bd26cad68246dba586475a5d521d334e263784cac1175df78fce1fae, T-24h eec13c1aa9cfdf2c71272d01a22c48b54df92be2978e007aa55d8ae7a218869a, cut a09eda93be7bfef70f96d1f522e2bd0d8b67397d083f9b94b34ffb153ff92e4d
- bc40c826d611929dc62b6aaeb51aa5eb5ce7f80b: discovery a47bba16bd26cad68246dba586475a5d521d334e263784cac1175df78fce1fae, T-24h 11889a7fa08b73ba4e219fc921fd094b5b858b71d2f2962b40339198bb80dadf, cut 14f1a7b19681f8b102dabe0a65c60e7588bb0edb63a36f0f30dad096d4d97ddd
- e4d250d22b17997a31a55499072a0c1c6530bb90: discovery a47bba16bd26cad68246dba586475a5d521d334e263784cac1175df78fce1fae, T-24h baca0a993cdafff31f00ae8540251d8a99305c0a996a40a761b8066a6cd7cc43, cut bd36f345328d42efec6645b119e44e90a3b444ed553f963923d2077bf19d872c
- f8fec350e7c19cdd16957d4699d5f01171793a57: discovery a47bba16bd26cad68246dba586475a5d521d334e263784cac1175df78fce1fae, T-24h 6c11ade4a83db0672c324cb2a3d7c4993cc807096e678d604c364ab36d193ec6, cut 5c8e179798998d591107a7bb4c95439172e98e2d083eb7fd7ebd8a737864ce3c
- 279ef1734a0021bb0f934f163b0044de0293cc61: discovery 17c317fd183d6ac7e05cc3d0fff7952436e6f3851b5896620669f9833c2e4ea3, T-24h a526d4e2fbd980881d2f4e06c127321e3c541983f2fcd89d1d092f3a8cee17d3, cut 90255d36b62a4600327fbc922984d088a3b7bed2b4d21a197c32c844a18aa3b8
- a2ca39d8fb18020a82d5fcf94f0ed3f6f12dfc58: discovery 17c317fd183d6ac7e05cc3d0fff7952436e6f3851b5896620669f9833c2e4ea3, T-24h 5dfda82251e18a8397a1ac6fbca675ec179b783888aa690733d7f078b0fd1767, cut 3068f0a6a25ba5d3ae2b866653bb6fbd82d9562253331c34ecf1ccf262d5f362
- b29d8a71ba0f2594419c0db4680e5d492cb3d071: discovery 17c317fd183d6ac7e05cc3d0fff7952436e6f3851b5896620669f9833c2e4ea3, T-24h e8b1010bab92ce455758f31f1e0192fb648b1f56d6676dfb1a9da62abc7bc61e, cut dd36bb1e46d9e023d2202e0f5e88f83ef5f76412e822270956e62e77a9763c68
- d7f5e5823924d3c7034d67e6654284e88f359953: discovery 17c317fd183d6ac7e05cc3d0fff7952436e6f3851b5896620669f9833c2e4ea3, T-24h 0d6bff5ac89dbe967bd0add4f7ef501d713a4ee4d6e4b182964baea4e5628d70, cut 59b77871c27d936a2883cdba5fa81a9938a5f882b5e0ba775d4fd53887acf75d
- 30fa767366019d7d175b420c8b6bd906c66d0152: discovery b2010466eb5734e9d5a945c2120babc014d1a5ad312ce4dd2d7451a27c67d25c, T-24h b3b560d9f7f78d760121e486c400d58545b2ad583658907687ccfcb6c653ee47, cut df22b0e0352aafb60eff3e3484518d60eba0065084defba34e376b30d4a69814
- 48d21e5bc31e83cc51fa0bab06384671a663d6ad: discovery b2010466eb5734e9d5a945c2120babc014d1a5ad312ce4dd2d7451a27c67d25c, T-24h ba54fc2142f92c2b1fe5c02448fa67c206daa3f7d4dcd35eb3a159adeef301dc, cut 4e1ad3106949477c363432891068d94c547ca85be84c072cec6acd886a2138bc
- 6a8291a98b0c783d5dab3e555c9190001fa490a1: discovery b2010466eb5734e9d5a945c2120babc014d1a5ad312ce4dd2d7451a27c67d25c, T-24h 681036270254f0bf3def5a9965e943284649076a9d7907142a9dd1599361683b, cut 12a6266be243a45fb1f6fdde1c977e4e21d899b8f0fd736869738c2f82a5e060
- db0894cf08e2d46506ef18930d52e3ab7593142c: discovery b2010466eb5734e9d5a945c2120babc014d1a5ad312ce4dd2d7451a27c67d25c, T-24h 318310eee102a628fdb940e27fe2e0828991feaf0949a8ad3bc57c96e5af5ecf, cut 33816d52d149b3b8db58a3cb1cca814b5411f10fbab15c2971f644321a9409ed
- d7e0d1358fa624004fd2eedb8d3f575139a94765: discovery 5f3181ad3544decedea6adbc30127a55a352aecde59b8a4b0be79f381d951cc2, T-24h 55901c230dc8022a1eba7738a3d34db9c72659c462fdb2aa5eaae0a38184133d, cut 2e814e9d6685c72f1ed21449dda802c59177f2281f1b48c615c47e049809b331
- dbf0bb73ca86ff10b4b5aa130f7b87d30c34a037: discovery 5f3181ad3544decedea6adbc30127a55a352aecde59b8a4b0be79f381d951cc2, T-24h e33546bfcf5dfcf336c4deba3d8182e69ef279a7827d85ba97190bf8129fd5d9, cut b9a5db7d57a1eab5b6d0206270864d49d40596be7ebea1cb585a6a17dc0904fc
- 61261f8407e4be43bf26520eb2a7df43135e8585: discovery c827deac550219736adc97e51d50b09506f746982b18d94904b89067ae34340e, T-24h 20102524ab16e58251161dbe2ba67b96ef9b5a927a9897393c2897f5f98d19ef, cut dcb5e239a308a398adea52a3286cb6d76c0439b5002816823af8bf893be16bdf
- 89d55053a976ee87464fe8b2e841e4f0da4794a0: discovery c827deac550219736adc97e51d50b09506f746982b18d94904b89067ae34340e, T-24h ac3cfd0b3b4256b63268d2049b2da80d2c5e066cb55518575ef4662ac42ba497, cut 06f5c14e5cf4e89872489466ecd6abe05980a2bb45e6ec9a875d4ed18ea17f2c
- 2dbb129a42e5fa9980f8cc9d803d29a3c4aa0243: discovery c3d550f09f27b146a2da103edeca6bf17cf7146ac2b8da844eff9f58895c6473, T-24h b5219da1b1ed6868a9a010e346cb05d8eb697b84334323b41ed9f2ffb30cd852, cut b82467c5c8310bb229ed4608f18fd7a9385845d5ffe4f8efb6fc099eab4d9c7b
- 6281d2ea14ea40e69c119868b6ccdb8f7c31b412: discovery c3d550f09f27b146a2da103edeca6bf17cf7146ac2b8da844eff9f58895c6473, T-24h 7d339a12c3bb4d3cf90ffaea193a069d958bbab17a051fa57b62e934c495c098, cut dbe6a72ec71eef5ec8438677a73ebe32dd106d90ad36e5275e8083ea92738fe1
- 54cb7fd2c9d5fa5fc605702e544b3d6745f1a892: discovery 2a7b08766ed7eee990ab8cc5eb248ba1f1f95ac8eaab5f486ea8c4260d9e137e, T-24h ab4632e4d15ef3bdc7685f521883a90071878c290ebfaf26474542490ecc9a08, cut 6028866d3b15383ca140464c1c2eed4f2541a3bd3e4689669b8c3cf404f41306
- 9e6f5c7e6368b17d186d32fbd0d5bfc5bc983d24: discovery 2a7b08766ed7eee990ab8cc5eb248ba1f1f95ac8eaab5f486ea8c4260d9e137e, T-24h 0ab606bc1bdf97163c45a12a0e230722a83783c29e5c104f7518f8d066a3e8fb, cut d7c0db3aa941d4f2c41fb482e248368976314408fe81a0cbaf072b8ac8dc8b42
- 46052d6799f2801f0fc5a40e66edb32a02a6cb6e: discovery 316783cb6d802b22156ca8c15546d859c2f8b55374f36342cc8fa130eb393674, T-24h ea4106bb34fbb2036fe4c993681aeb587a7f907f4e0634dd484703aa9c978fd2, cut 83cfe40ce45caccb65d364b3b57f6977d5f32660cd08c0c1bde3938582b12d22
- b17b434fc9a62b4000f9baeb2ba1b9243b37a89e: discovery 316783cb6d802b22156ca8c15546d859c2f8b55374f36342cc8fa130eb393674, T-24h c403c9beb06a21014fa2642861320809b5e5b5ee74ec8dd4986043e099babc62, cut e24f016f7b693fca457402292b342dfcf2c2c235cab13f4a371943090a8668b8
- 01d09baddc5ac5e7138a13bf15743eec60061a62: discovery c61a87fc865c729fb22dd25f2e75eb96bef40f30f6c4c29e523e6ac0ea5c0ec2, T-24h 654c7c44d833544ff63d68bd252be08086ad0f4d499a930c9ab63c9178ad55ee, cut b2889c599d0d1a5f9fb792d323923bf5acb4a3b687fa5063f701828ddd0c956d
- 1d84c51c953e05f422a49cfa9ab9dc603c4c537b: discovery c61a87fc865c729fb22dd25f2e75eb96bef40f30f6c4c29e523e6ac0ea5c0ec2, T-24h ef4a0940959d56f31fa987476564952d127527d9d41be7353261f0ad9ce6b844, cut 42c2a97c314f3a30cd0c5db68486c3488564b6c34a2c15fbaf4f88929ac0fda1
- 008cf4bd2d440e5954c606579070f59ff944d729: discovery 373a41bf05bed148bd9a13fb19b5d56bb6bae4d76da6d21c3a32278d9312089a, T-24h 1f9034c65691792d13ba1a8476c725ff0dad7e0d7b68fbccf3dc035ff7381a23, cut daae7adca304dcc5331e643d36d5106e1b10df9aa8c3f5cf082a6b1bf271a56b
- 316d0179f1b890b70065170f698ff8c3ed13e4a5: discovery ff57d224194d2ae711c6758790cfe1e9e650bcecaebcf68abe4d12437dbcde84, T-24h 9057415823f9ba6495c28ef1626e4f08213c0f19cd24f3581091e6f9ed1b6706, cut c6245b6ec73bd82455e174682f71edf3dbd703ba3c4a99063317c9552cb8bf61
- 9b2ff42a36b22ff8ba53ff3751de4c8854207b81: discovery 4ea8cd016415b1857939023b3f9432f9e09dad8357a205935ad1c13a2b851a7a, T-24h 6a4e70e51c11bd3d1e8e478a617e093482c4707bcc8f5669f4964a6b93a4682b, cut fcab1e55e7b39d10f07c55070db7fe2e9675b96b1a65f8a8632f80b9156029a2
- 9d928364e19ec4ba59b0c4d8e061c277aff28f5e: discovery 320bc0851899a87dede2ff08443fb00a5ef61b7beaa068eaa2e156a0d79ddc20, T-24h 777c3b27c7ab2aca9ce4aaa7bdb742278f7366256d6b033b2760fc9f7fad93c9, cut cc682765a053a0040d296a65843ee03ecabc293948bfa5fcf1852e62b7ed5653
- 4665c4f6561b9bb6f387ba8b2df5d3246878fe81: discovery b909ec4f00fb22e8638d0c09d06ceacae70329373166ffd07fc7151412c5f940, T-24h c5a5664660201b31ee9bf3f966272423b9dea7ade2988962f9cbec9e4016f048, cut d28fe4ee43e935f384fd26988e22c2343a25a20649c5e71d88023a200a91e450
- f8579bfd674caddc6f10d425c03287fb0dc01773: discovery b909ec4f00fb22e8638d0c09d06ceacae70329373166ffd07fc7151412c5f940, T-24h 624e7142f77406e352183fddb883f86d5057858615e5d1b6de5711cace893c31, cut 6f1158db1271170542b2db766c69530d4bdc137bee032f465d41c26d139073f5
- 1dcf1eb3f3506fcbf80b1b1575af99afb7c8a659: discovery 7c68db0f814032b53427868f63ff69f8060ef04b9be32733cb5172c7abd8dcbf, T-24h 229fb19b6b53928a96bea23df9484f214aee9d54b66af55591e73cba40b22b9f, cut 49d694924c7a58b406a962cc88508e12f8a89afac3d945a6d8c631a81bdf29d3
- 8545da30b9b30223258edc1a9f7835b5b126750a: discovery 7c68db0f814032b53427868f63ff69f8060ef04b9be32733cb5172c7abd8dcbf, T-24h 4fef88d35d944223ea4a3e3ced773b0ce62ec2b88a4772508fee447cca76ec60, cut d04d36a0652a422e428a6eb24a5058f0e791526a84d659c842dbb76e72bcd6e3
- 14ee9254ce94efc1f1c3808602b4089aa5f2f921: discovery a65a1cfe3d07f4e2f21d3c8d81efea6a0da602e03868614c671e49b112389b91, T-24h 707a3bc54b705f60ff58d1e3e7a1d016e7559f9f0033b2fd33f3efee3a95aa2b, cut 18f12efa4b12c54e67aed4156e146cb49ff3644a5b44bf94237f227be1ed6c2c
- d476ae60b7f2a6deae135ae716a7da09ece07fa8: discovery a65a1cfe3d07f4e2f21d3c8d81efea6a0da602e03868614c671e49b112389b91, T-24h 0946b1ada65d1059b3275950d99148570d5b8d26d9d98c1127f938f4d9d339e5, cut 2192c7a87f9ea4ee2de50384a99da297e01586eab3fa276f7579a758e201302a
- d755f75ec84901127a779218fe5f2d186b89f2bd: discovery a65a1cfe3d07f4e2f21d3c8d81efea6a0da602e03868614c671e49b112389b91, T-24h 7b60c3127021b1e03fc6b00180920721c6baac172ffaf870692a7461f38505d3, cut c5554099c37b6c92c31b7a6069035ee9b7d1d4225cd721b4cb38a74c47fa03ac
- f9f72b02c7f1a906e17bd5e3e09f3d2b55e4f941: discovery a65a1cfe3d07f4e2f21d3c8d81efea6a0da602e03868614c671e49b112389b91, T-24h afa114eb5ac3410b6e2085c33129bcbd98c623c40af2b60e97bfd7bbe63a863b, cut 9e19017f04cc873b7491ba3eeec2c41c40d57f8db7e18350d89f69282bfc94ac
- 243f5b8324ff283df64537f7d559b72bfcd85b95: discovery 61b4471d48e0d4aede4e6a4e3b5e75f433928a4837e0b6bc860e75b3f6a42655, T-24h ac01991ee2d8095da18bc8fd99dc2a1ed7d77e736b9cc49a15e383feab40e61c, cut bfcd04bcab24767ee941d0ebeb61c75fee4ae1a2088095e971de3dc21b2a6bc9
- 588cf875eb38a6ac836ffcddac459fceaccf8c31: discovery 61b4471d48e0d4aede4e6a4e3b5e75f433928a4837e0b6bc860e75b3f6a42655, T-24h ded9bfe8ff270bcd7324d1fa35183ec79047d5036a286db9e7ccbcab3bdaee5c, cut f87d9c33186f08b8f3af72a14dd04549f67a3bc47f0cf18a461c353f78045e32
- 7072f1450b95a8b5cbab43ea361a97f326f609ba: discovery 61b4471d48e0d4aede4e6a4e3b5e75f433928a4837e0b6bc860e75b3f6a42655, T-24h f23101155d460ff5f259651bdd74f9b6111240a19d41da24cb10a870147f1192, cut bf9bf11df4ff3b723dd772a4e0e735a324b2aedb7365016e780bb07876bb83a5
- 8b0448e0fa46f999db4b565c9d669ff51d9a12a4: discovery 61b4471d48e0d4aede4e6a4e3b5e75f433928a4837e0b6bc860e75b3f6a42655, T-24h e1a8132cbf80ee97b0219f9fab16f59273f3ec8d1a75f6eb1d4497ab5c15f865, cut 891762c29b3c83838b8efa6dec6d311304c6195ad558f7c2eceaa260b6e22efd
- 5e526c2cc95ed001d3f6d99f53b63a0d08dbced5: discovery fb4935c4bcdf4835c4bb0aa47f640127281bdcbd4670412453ecd36f8ddaea51, T-24h 377d5574bea8c963558d1a438d71e799a64bc6982379f0a7c4d28f6817d44264, cut f59f4fd6e54f167a59e18e47d56165ee00bb0a0fcb69d58ddeeb6baeb0d6bb28
- 7ca4b198971b9a9f47e847a485a03f441619fc9a: discovery fb4935c4bcdf4835c4bb0aa47f640127281bdcbd4670412453ecd36f8ddaea51, T-24h e00d8a288a1a682735ae8c8b7e65bb132b2363b0ca3cc9ed9306f93b24ab43d5, cut 4f60f66be0fa0420c24556eff1d5a51c32eaade4659337576103906ed308ac60
- aa399f0d6081042b4c6410549ef3b6d563f7c959: discovery fb4935c4bcdf4835c4bb0aa47f640127281bdcbd4670412453ecd36f8ddaea51, T-24h d0e7e121cdede89358b7eb6f04b72132050f3542d6ad101416314937293a69e0, cut acac23c9b7365a39b788ad6de9f4004b6e313a0d70f87c997355c085f00c3591
- f3e6813676b4d683ffdbc1914a61cf9b124c31a5: discovery fb4935c4bcdf4835c4bb0aa47f640127281bdcbd4670412453ecd36f8ddaea51, T-24h 626d2a8b8b48c419d07de4d9b61b6c1bfc6f5ba0eb331cbe2689d2ac889d73c6, cut 8b14c512954c62d16f519eb9f8d5014f259a621051a9d2a579d99f01fdfd787b
- 4c1d85ac8cfcd8e883b231b191f671367c6a2c35: discovery f36432b3dd0c244337857f2299ab72e0ccac83000f09690cc9fd3e53143ff9c2, T-24h b4adbacea56bc0e6f1322c70f279942d586457b5e53f3453f818197557468d01, cut d14c912a4657d7325a1f89b9b96e20a87aac5aa3873af91cb43e6be8ace881c5
- 7ee7ab79d158565b34545289e15c16801724bc90: discovery f36432b3dd0c244337857f2299ab72e0ccac83000f09690cc9fd3e53143ff9c2, T-24h 41c2a6563a329a7ae28d7683efdbf5c39a143aa08f718bfe14866782f94bd71f, cut 92ffa6870e1a15166f44b986f41adc652e9b7c08fef69cd4485292566332e8c3
- c761f1f2277d860f922ecc60e63898806fe81cf4: discovery f36432b3dd0c244337857f2299ab72e0ccac83000f09690cc9fd3e53143ff9c2, T-24h 8da4d5d948afe7d2bd21ece9fa623b3a3a8ef1f8a3e6c528f7e6ad6055091c6e, cut fc3606e21040f1e4d31ee33cf94096946d0fad2da04f61d02547006ff96b4a7d
- c76388393d828cb99f56dbacd81721f2b13b0b4d: discovery f36432b3dd0c244337857f2299ab72e0ccac83000f09690cc9fd3e53143ff9c2, T-24h a5833cba5b5c634911b51e82f567dd8769788cfe1780bcc92098203671743f6f, cut 58d365444c6c629cd875c92e8a8f117acd00fae48be152c3410a194fdb587e9f
- 30f35f556e2c7d03adaaae3dc03b6f596f0ad800: discovery ce1a5681f4deaed269f09f43204740807f920a448b4d4a5587d97c8057902e86, T-24h 96b072ea160d887789a4974a817506ee420a90453a9baa03dbe142802a5cd95e, cut 034685298d98c09bd2522d323472f3480b0dd1ceb85060c768eb26f1787ec269
- 69f35b88b479ed7e041cd9e56978e9ec8520dcf9: discovery ce1a5681f4deaed269f09f43204740807f920a448b4d4a5587d97c8057902e86, T-24h 2513971b1a6c44393dedd1e270de9006a90cc25b1e1dc3fd6c85cddbfd585cad, cut 04eebebc8b799af6cd0c3f4e756046f7dca586b862a084221108ffcadcb8e433
- 872b8963859d7ed357666a8b602ab76196992da7: discovery ce1a5681f4deaed269f09f43204740807f920a448b4d4a5587d97c8057902e86, T-24h 6c2c25f64ccbbd6a73c1f12b4ddaed2e508fcd527f77328e079a052a508988e1, cut 707821d7d048a60a44b4741b85a3eaed5c2bd44b034aa84a12936d34b529ba9a
- afdae26c692dce8d23ae250767d4ed39d780f74f: discovery ce1a5681f4deaed269f09f43204740807f920a448b4d4a5587d97c8057902e86, T-24h 4d5ad91b6e45e91ffc504985f6bfb9fbbe04ddd4fd09106d4ead613e5df4221b, cut 32bdbfb235cdac28c743d3b9cd80106eacee0c16cbe29fd884aa92bbf5f29862
- 4771355b225110b8efbc3afe209af0de2898ef9e: discovery a391bcca5188e352b7ff9c94132442607fc03bdc7122ec37f3a5b5a007fe0d7d, T-24h eb556610a5b1845d94de1154166a1b02847a49446f3ea075c6b8b9386f7b10e8, cut 37b002045c2b398dd5efb385dd042f74becfc059c53797116fa8e8de07bd4bd7
- 92ba0f99f7e6a499ab5d2ebaec1f557a85c570d5: discovery a391bcca5188e352b7ff9c94132442607fc03bdc7122ec37f3a5b5a007fe0d7d, T-24h 0e5f7d8183d31978afa77a59f5a5ead8ec3147387d01087471dec0186daa9b4d, cut 9bf93c903722d127888b13e44e9d0daf9c3491fe63723afd131f57477b102fe1
- b273c3664e788b102ebf20a449eea642805093af: discovery a391bcca5188e352b7ff9c94132442607fc03bdc7122ec37f3a5b5a007fe0d7d, T-24h ca88490737c11506a100fffa4e8dcca7ea38c8f068fb1f8eef50b325881c1e9c, cut da51714108e61081424b58a28ac12bff9041d0c6b89fb88800cc7b7a8b4562bc
- de47949dc234512639f8386f3a952f454ea1a4ba: discovery a391bcca5188e352b7ff9c94132442607fc03bdc7122ec37f3a5b5a007fe0d7d, T-24h 178e43f7da6ae3145a4cf13ec42c5e1761a34b9c1f0b956dbb09b76a71f5e03e, cut ca1c511834f48089458b96ca1cfa940f0ced9a43dbc501f526d61515d1886656
- 5365e9c57caa2df1c2fcbf8fa33b9a30fcdf5e38: discovery d07bbc6d7453e4883895153bcb386cd8afacc435115e0c69b3bbda1ea8fbc006, T-24h 2ecce016b07fb838025686d23bb4ed101ccb45ff48252c25d26a8138eef759ee, cut 85314050757a4ac2a3ae57b75d2c76d17a6216a5d9fe271fff8f2f08ea709a70
- 8df629496044e0d784262e0a0c02bbc1508ca77d: discovery d07bbc6d7453e4883895153bcb386cd8afacc435115e0c69b3bbda1ea8fbc006, T-24h e3a980f50e876467d512e66b9f565ef1a072f6b3c28e635acfa8656d77a150f8, cut fcd5a928214ef038e379e269c46a0acf0770303ccbe71d61de5fcdc2008db5de
- 92899fe6efbe5884a25ac27fd0a7ac7fb4794f7c: discovery d07bbc6d7453e4883895153bcb386cd8afacc435115e0c69b3bbda1ea8fbc006, T-24h 5e63347d65635ee3d64ac4013d99842affb276acade40f14c12d2115033ca245, cut daec85dac621920ecbe84e00e90e885f8c9f2a42d3e46ef1ebd12f151eb9938c
- dcbddacad70b5b7513afd143a2dbc0c5b813651d: discovery d07bbc6d7453e4883895153bcb386cd8afacc435115e0c69b3bbda1ea8fbc006, T-24h 4b0b7e2e396596f87279908f767bfd4f382abae90cde366fc44f6f737be851fa, cut 2270368a613c1198ff2699a5d217a99a4f44530f5e6392051fd9ffc7a6f635ea
- 16f65c4191de4b97cbd3833b7276f5d36704371a: discovery 84a8dc22a70a316146d5d40285c1f7d00772b2fde7a112dfc4dbefeaff92bfc1, T-24h 742ee0076a48210f92f26a7fdb0d35a06a47e430a9753cd26d33104b300ef9e7, cut c77fd6786334d4c3f8d18b6ccc64673f85725210e2a9e8d70b679d0f7b8fbaf5
- 21b46efa403787487d77f49426f833c6d2b13e85: discovery 84a8dc22a70a316146d5d40285c1f7d00772b2fde7a112dfc4dbefeaff92bfc1, T-24h 5e335d655d8ded227f27c0fed0af2429b1af927a9259bcf3c874a72c7e5675ea, cut 9911ce01f805cf0a3b5b80398d7669d501106b24a0dc422abfd32bf3885e8159
- 7565fe38446f5ef7d203e24bd45c281e80f33bd7: discovery 84a8dc22a70a316146d5d40285c1f7d00772b2fde7a112dfc4dbefeaff92bfc1, T-24h a790245334eb9618608822dd6596ccb08f1358d28706e07a469101ad74a50bff, cut 6781773dfa45eca00e4dd2a28cdbdd5cccac2573ed005114cfc41159a32d6e0e
- 9442c30263ec96be060aff45e085a8e7d1b96088: discovery 84a8dc22a70a316146d5d40285c1f7d00772b2fde7a112dfc4dbefeaff92bfc1, T-24h 10e0e535a1602ac2246f88eb8fb942fcb93a1a10c3cf17f7f0d6f4e8c5f936ca, cut ac497c76cba1528bb1d25bc5df1167bb7289c32c8e956eb9a6d1c6c2e37c483e
- 27a4e4e4dfdd07fddb9bab56a0e8b0ec183a8513: discovery 36cd66d25101e3bcfe106ab25c0a5cb84fedf93a2c48f2903487dbcf81129506, T-24h 8e4ce9eb691d7a918cfac4322330432a0c575eb583ac065cea34fb7eef687b55, cut f00ef87fde26031e31c5faa8c358da673a4d31e61db6856a11dae69786fa32a7
- 38b78c2073f7910ef0b8dceef35e2f464caa5e6f: discovery 36cd66d25101e3bcfe106ab25c0a5cb84fedf93a2c48f2903487dbcf81129506, T-24h e4d7adfc7aa62bf728c9fbf41243f996b18d10d51acddb6caccee4659c1a6034, cut 79bb2b7e6b271a86e8538abdc9b28fe575a0c07c4ef64f94672c92e0651ffe45
- 50a595ecf9024e7624b4a6c8ea315f03f447359f: discovery 36cd66d25101e3bcfe106ab25c0a5cb84fedf93a2c48f2903487dbcf81129506, T-24h e62868708a244bcecea3163ec644c77899b403dd7ae95bb94126f9d003ac35dd, cut 2689b1f3309b30d0a9480df070bdad1f157bec29ad3419dbfb8b1a6695248357
- a8b7a79bd2a2ee40ecbb5f06e4bf9d2f4c2dc3b9: discovery 36cd66d25101e3bcfe106ab25c0a5cb84fedf93a2c48f2903487dbcf81129506, T-24h f4ed2ecfc1adba546cb1f31b2b18c3b4a7c9507e7104c238af63ef9f47ec286d, cut 1c783dc781d2547ef58c00f2ccaf21210e1021b8276fc42ba747ee81d8f279be
- 3d118aa564102ae41569900bfb551eeb7014f08c: discovery f9dc6cbc3e3daac743308eaa47a3100f3e7d98592e1ce83c5d73e0a74ae66a62, T-24h f5bca50af8e6fbac3b9a595017dda8daa724588fdc4836e78387bd328bd007ed, cut f538c62fbc3e3422b53956b5f981c8b4bf70bba806d1ff1cc6acaa897977248d
- 820d159625eb1de05a5b635ddff3b69f84dde55e: discovery f9dc6cbc3e3daac743308eaa47a3100f3e7d98592e1ce83c5d73e0a74ae66a62, T-24h 2c44f0914f9f215bb86312b79f61e039610b978e8cacc954057e641cc83d7bc7, cut 36065f4b113230d86b9f8a3e20ef0a25e20bf35f723f2425f5ebe5717906d3b6
- 9f394806dd80d188b09b5222980569d799d075de: discovery f9dc6cbc3e3daac743308eaa47a3100f3e7d98592e1ce83c5d73e0a74ae66a62, T-24h b748942ee0e8fe4c717aa159dddc2e38d6760499a2e04a1614b788f206ff8fbe, cut e37f474952560d502bf0e6767641f46f99d2dddd2fcb0eaa21b81a8929c0b941
- e4c6aa97ec621afcf067968d7e4efed49d80895b: discovery f9dc6cbc3e3daac743308eaa47a3100f3e7d98592e1ce83c5d73e0a74ae66a62, T-24h 6ba5d45c5dbab635cc064d53d910f1d79387fa0b68a8fd0b44fb5a31674f60b5, cut 7104529b5c40fbb22244940579eadb44c9f5a6213a5189e25375180a3119787e
- 0fb2adb3893ec393c582c3c9e4f7551e3df4a6fd: discovery d6f9552fd4937a6867a92fcf5a074e542882b45d729a4f19fcaa4899557e8c16, T-24h f3b3a5a9addada7555d5fcd90d0711adf45ede2d920d0c1945c5ba79c4998965, cut effb48c4ed7737c7ac4090f2df8d427c7b6e1526f858f923adf930a45577ec1c
- 5d50c50cc1d9f834fe7bfd0b0f1e482ef65635dc: discovery d6f9552fd4937a6867a92fcf5a074e542882b45d729a4f19fcaa4899557e8c16, T-24h 223087dfb3042cb5bfbdedd2a7656bb8e6318fb094fd222c6c8c2d176002aa81, cut 6da23cedbfbcc386a0364b06d638c28e5c0e94eca0283dbff261812338943a3e
- 638780222010ece684245babe0fd1855fa31ff38: discovery d6f9552fd4937a6867a92fcf5a074e542882b45d729a4f19fcaa4899557e8c16, T-24h 2f043c0e57b38bdac13c919b16c8e7189148a8630e2271dfe184a080b4a6ac66, cut 4026e744bd56beeb433112d9418c4f10d52ded3282038f2b3abf6040e240e7e5
- c4ad340ce7bebed61a5edba5fe5274785744187d: discovery d6f9552fd4937a6867a92fcf5a074e542882b45d729a4f19fcaa4899557e8c16, T-24h b8258f6303dc3cc949d2cbf764620654b93a74dff52196ad12c8ba82c901b9cb, cut 44a6c8bdbc9bf55ae93ed125a5af3f98d64ae7665ecfb1ace00670b9c0e02887
- 02730a4b55eef8c87d258b4c7e99e57938f593ec: discovery fe0389c32354c61f5f11c4ef8f0c603ebc2d5529f65924ce35a8ea5eeabbc29f, T-24h f042e979dc1c65feafddac7f806633b466ce87acaa07486330b65f35237cf253, cut 89f7633bb00503fee917a7f0c87c99ba289726b86249e0961e7b810a0a14afd9
- 2442b6f1d32dca00f2f22b2ac4c1837c621035c5: discovery fe0389c32354c61f5f11c4ef8f0c603ebc2d5529f65924ce35a8ea5eeabbc29f, T-24h fec3b47a752499ab3a6f294fa91ec68294188c6d44a7640dce25df6bd6ccc674, cut 17b688c67716188d47a86986de40d6a646c0b6c76d892b07eb6070d0e4efb353
- 637d1f7a688e208c91c2f240d7103ca8b48aea1d: discovery fe0389c32354c61f5f11c4ef8f0c603ebc2d5529f65924ce35a8ea5eeabbc29f, T-24h 9a43e38eaf2acff2fa2211fc3f907cd5db30d4b9a1254b77321010896a4c4c92, cut 67f232e9667bcfabe9e8d1028f484488a65ccabe6109cf6a4aa152c4b1102830
- 95c6c59f6de6e1fe4d0f8409e65b485b5205668d: discovery fe0389c32354c61f5f11c4ef8f0c603ebc2d5529f65924ce35a8ea5eeabbc29f, T-24h 93ad0855fb1f5741c3b2d35350a6af5f04370ff7cd46c2861acc0f0516283df3, cut f98efa66bd669ea34b0f1f521d47c73a1eef94062c9738de349e2ad4b3a8651b
- cc81d365a25ff7cd94682e56cbd5d54d9e223cc4: discovery fe0389c32354c61f5f11c4ef8f0c603ebc2d5529f65924ce35a8ea5eeabbc29f, T-24h be81076a61e44be361625c1833cb6ce408ff305594490f394da729fe9b0c802d, cut e7044c57b040f681969dbe55511665588f7e716d6efb2634d4d2df9c55fe40fa
- cce9e1e464c4c4f4a10f3c2b64fbd69e10d3d113: discovery fe0389c32354c61f5f11c4ef8f0c603ebc2d5529f65924ce35a8ea5eeabbc29f, T-24h 94b2b6058fec97b450efb2d218bbef6f2f7b96c73735a7ba583d238ed765a0fc, cut 5eb96578634a00447286fc510969fdc4072da59a4aa4ac69ef64805a846cccca
- 07e754a7cf28afd0f9b9dc34c5f6fd084b96f93d: discovery f039a70d725e2bf79b794c73f392d048570174bc44c8e679fab0c876818103dd, T-24h a5bd9f686baf344a995a52314994a21b14fb4596102ffbb0e12ef33fb555004c, cut e660800fbe8e8b7217bde4b0e1e9929a46421db0c674896e8e97d1a20ee3de3a
- 487c4e8007e26297a0c4c5aec16da5c6a092eede: discovery f039a70d725e2bf79b794c73f392d048570174bc44c8e679fab0c876818103dd, T-24h 5f39000fbaeb49a934210c9e5ffd878a9b6ef472acf6226d819acb5084be9395, cut 0efce97a3c456779ce825b18155ae51ae13f286b1d9082f7c3a3fef64239355a
- a280adc3d9dee0ea11933ceccfe1eedfde9cacfc: discovery f039a70d725e2bf79b794c73f392d048570174bc44c8e679fab0c876818103dd, T-24h 70cbd28537c6f59b8108e3ca63393571b24eaa97b83be5d8d4070a714cb86e98, cut 1dd2b218cb9bfd546ae82d137ea78ca6636eb940e1af86349a0aa8f4865023ad
- aab2ad0a1ec8c82df334119c12a7b754ae37dd90: discovery f039a70d725e2bf79b794c73f392d048570174bc44c8e679fab0c876818103dd, T-24h 92c180650188f681de90fd4885472c6f83155e63ab072afbad88f714d0a05d72, cut f786e62cfec773426c3cc69ea1433dad47468343641494858e3c418323b302c2
- cd0861a19924260e151d186c64ae89daf04774cd: discovery f039a70d725e2bf79b794c73f392d048570174bc44c8e679fab0c876818103dd, T-24h 6f5d89ad5ec57ef779438f87e1a0e2838f22d4efb0ed6556059e4ed8cc627ddb, cut b16002610cd388873cf80584061bc5c3f1c2f86bb236522e9738aba80b769391
- e9bcbd747345346d31bc7fade84b45947f852c68: discovery f039a70d725e2bf79b794c73f392d048570174bc44c8e679fab0c876818103dd, T-24h eaa94b5ac120cd406ae548c37ee0d167de8b2ce8e6c985a226b6014cc90cd7ad, cut c0ec1fe193a5002f65f6a24ef2b1bcf9ea6063cdcc1fa35c45af074cdebc8c16
- 19be1f978eb386a07ad2011c728272d34a7e040f: discovery 48ffeaaf8b25a8c95452dd3b64e4c6f3a422b8d50712a394eebe8507181d3ae8, T-24h 42146c6650e5f934e0b3e25922b40a6f5e025ef3b982859ac41d6fa7c7fd10fb, cut a7d3fc93ae3f734ed976509bdd6f8670aeccf7da569fa0da109ef6de10bfa365
- 490b0b2971661a3525043d702a5e6898389cf6ef: discovery 48ffeaaf8b25a8c95452dd3b64e4c6f3a422b8d50712a394eebe8507181d3ae8, T-24h 386a55dfe202814deb367b87450de40388f82a71bd6e20740f507d64b572fe74, cut d734ec257673b51f9cb6e653167bb59f2cd5e756b95825ff5da935ca4e85919a
- 7933afdaeb97b731ed44adbe221ac616623acedf: discovery 48ffeaaf8b25a8c95452dd3b64e4c6f3a422b8d50712a394eebe8507181d3ae8, T-24h dddd0b517911197b78181e2874f65e058886295f9df2f8643b8a1fd5ed95fffb, cut 743d8d6b833f49b82d2b4d1490d64bf4cc764e2cbedb89a41e1af8de2761630d
- 80a1132c63e6025875eea4bada2f1fb523f3e538: discovery 48ffeaaf8b25a8c95452dd3b64e4c6f3a422b8d50712a394eebe8507181d3ae8, T-24h e42d72ae24be209e84e007690c1073f9d5e2a85bf60e147019be8b7acfbed0d1, cut 003a60e35b576f48bb6c74a189c626e26156b425d7f6b84e721ea402a87f8e71
- e489c6066f03837e961655afa7bd37dc1a81275c: discovery 48ffeaaf8b25a8c95452dd3b64e4c6f3a422b8d50712a394eebe8507181d3ae8, T-24h 6682a19995a0de5a8dc140f984f51aa85d362bac0cc1b66348769738ab1dbb19, cut c11805825a3575f46f514493facb720f507a203d9d1ace1517046d65265ee1ff
- f360a381791923cd80583f9a0ae78b464765a30a: discovery 48ffeaaf8b25a8c95452dd3b64e4c6f3a422b8d50712a394eebe8507181d3ae8, T-24h 17ee3516b31026f84d6e2801e8c8e2bfe0b5554cc66eb3b53ed9a6dd28aa1b3c, cut e86fe79083527824376ea343d97f48fe8a08625ec699215beb769ace9c8b5cf9
- 12f1ff8ad7c417c50bb9aeede0372dc7e755e939: discovery ef5ac24f7bed2c5bc6c01d2807c43646d7281c1710c35de1cba816363c67d623, T-24h 246f4de5187f771d16604fa177c7ac8c535111f4ec26320c66eb284d0a6fc0fe, cut d197767718c66b61db4ef02d5b39549f7d052b31c106736315fff70e75483c87
- 3e84bc7c6f06f9295042a873ae97d63e18c2ec86: discovery ef5ac24f7bed2c5bc6c01d2807c43646d7281c1710c35de1cba816363c67d623, T-24h 7aeb5c948cfb56235ea145bf4e6dcd62221992e2aeb8d4598f505f1821d7035d, cut 95d336e7c8dc92154323e38052ff88a9271e41ec9b3cc5defd81e612422e4610
- 670ef54a7b6ef9f2c49ead26e0cfb19852f47f09: discovery ef5ac24f7bed2c5bc6c01d2807c43646d7281c1710c35de1cba816363c67d623, T-24h a2b81dc203461ffbe9a4da28688aa3dcbb1d8c240a9e4761ed84c98a13ade88b, cut 024085c4ad1b48e831cd83f847028f611a1da781de84b5342acac3996d888605
- d9a3072856341fab19c57eb1077b8cf129dd30cd: discovery ef5ac24f7bed2c5bc6c01d2807c43646d7281c1710c35de1cba816363c67d623, cut ae207a3e6f74fd5d83a4a6b05a4e963b9d1979bcd37b361e3c47882b25d17706
- de7542a3691273634d9ad12d43e67e7cc665f257: discovery ef5ac24f7bed2c5bc6c01d2807c43646d7281c1710c35de1cba816363c67d623, T-24h 0919a82c9e1eb25d6938a410aae32ef3783961518d5c1d1974bb13f97b189dfa, cut c7caf401f11f68199e64ef42d42758199f2c1cfed48d98d9fc6700409c9dec27
- dec324b195b0c21a6c49771a198fca878ed0f2e5: discovery ef5ac24f7bed2c5bc6c01d2807c43646d7281c1710c35de1cba816363c67d623, T-24h ff5093eec3083b72a1ea12e08039c3ae81f3a55659205b172482268c6fa959c1, cut 4446e836a84997041b1c17f6db15ec7d9e69920865465a3019d5a3b4427b5b2f
- 8af992f27f664fa66df38c6f20b990630458de21: discovery 3aae3bcb20aa5c6bec8a2f6c9ebbd0da40ac7fbadd27d237067c76ab1980ed59, T-24h 6a0d8d4388914cd53ff3d0db11c4d26fcae3136875ec449b5692e33ce54e6843, cut 250427885476f00c53e926950c54d86c0e39da6823e97a82adfd8602c5619860
- 3c58831a4d03ae480d1e8936b15c444383852826: discovery 7e65088ca0a5d604a76c22bd474e5725a7475ff1f989872e2c09a60ff39ff39d, T-24h d49c4606ca9b2394a0fab917c91c9ed35b465dd50b37d209a81d23993c6f81c6, cut ec34bfb35c9761d49cfe49825abb3122d174c7fe23bebe21530cbf1d0da074d8
- a567d17d493ad018b9cf86632c05eb416ae250bd: discovery 7e65088ca0a5d604a76c22bd474e5725a7475ff1f989872e2c09a60ff39ff39d, T-24h 55bd440c914d043705089d2afbc8de86fe2c2d9753c19655ae7742695f88ce57, cut 290f609e67af1d198eee15e8d3040cc16aba43e348bd12ae4d8292c8f8cacbc9
- c46fbc39ac9ca605281d5631fa223e650d9b20e7: discovery 7e65088ca0a5d604a76c22bd474e5725a7475ff1f989872e2c09a60ff39ff39d, T-24h 2d64d162fa3701dfb0ac2bc84eeb32490a6f50a5905a6d90dc33fcd2bab4a18e, cut db98be0bc36d91d3a533b5d8999e8abf8d4e3310aa64d64867e115a0bdbbdd3f
- 043606e4dda35aa9f3baebf4c7be2b065c863870: discovery 34c1ad5c9afeb5f44d82ae4fd686e1ab43942dbf3810118356624a66fbaf5c5b, T-24h c54f748ab90a5169e5589cb976786651638538b2c05142291a4fe9b86081d56c, cut 2eb7035c47cb7e6571e6464ff8d249259b353390f0a4443dac1eb95acda8c2e0
- 46c1bed403e3310a7fb80ee345a8705d79693555: discovery 34c1ad5c9afeb5f44d82ae4fd686e1ab43942dbf3810118356624a66fbaf5c5b, T-24h e2b18aefe140b05e85ac0bc2ad01bff285f3e38b6837a35c35be43b70d31b642, cut 25e831ff1bc1ce44c998bd88ea9573818c0a2f0d755255ba1886b2b2ac6cb734
- b130ef4912adee6567e0cf42ed9855f618653129: discovery 34c1ad5c9afeb5f44d82ae4fd686e1ab43942dbf3810118356624a66fbaf5c5b, T-24h 873897aced85079a2510829fc77b693aaf7c4201d063448485e097c7cb1d0ae1, cut 79ad5eb25c8e87b1f2674b3a0cf47bdb08d47a6363fc1c7bab375c5bd73fddaa
- 17e24b8b61dfb57a36eff5107bc8a5f154d3412e: discovery 88071431458d8e74bf99a0c6bbda2744b2857530e86f15fbd00758b26235d601, T-24h 842fe74e7baa8c062cc09083e4e22668ca55a54240772709359047803972a6df, cut 5d4029e3055ecfb2a9698e6e77fefe2088223925dbb5b10f1f85dfb20c7b79bd
- 974d18c1ea8951b4f40ee66a952926451a36539f: discovery 88071431458d8e74bf99a0c6bbda2744b2857530e86f15fbd00758b26235d601, T-24h 8b0fb9d11a742b4966f0e3018569b656d75aa4cf489d2e29b7c954ec6a77ed20, cut f557f69abb7fe26e91ee843458031d05bcb71c8c33ff06ad4ea9072fc304e764
- ffbb0cfc6b89221ad5a3d233514bae52e025676d: discovery 88071431458d8e74bf99a0c6bbda2744b2857530e86f15fbd00758b26235d601, T-24h a61058191ee65a9bd53990c6fbf8f0110e62cb1827c43c13e06de919a31b4908, cut 25f08da633e1d053a16627bce9a18daca9c301556d65fc14dd7543ee3ccb32fa
- 6deae45a7c9723f5f778df18d732387c83ef2da5: discovery 0ec5943108dcb00a8d78ef1e596d58b9b0a89286df385261212116b566872c6d, T-24h 2cfde2b64001583509a5e0d726beb80aa4ec16b9b803c4233274847030b7d440, cut da2fbdb43dd43558cd8d35c851e88435d7747c510f289acb97884441ef9a3b9b
- 9e8e8aa9f3cf3c2aa0df79bd1c98f4da6690c3d2: discovery 0ec5943108dcb00a8d78ef1e596d58b9b0a89286df385261212116b566872c6d, T-24h e1e2a38af97fa6a5b2d825215b2df145aa8369fc9199335e0aef602eda33c78b, cut 721e12d1c9a5dc9e5b52df554a67ba8e1bfa35f50f04b79ec32577d34c2c209d
- ff807b7bdda744a6104115779311f321552231e2: discovery 0ec5943108dcb00a8d78ef1e596d58b9b0a89286df385261212116b566872c6d, T-24h 03318b274419b069938ab9d3a77b85b5a815aa8e3d3eec7cccfabc5c5e379db6, cut c3f0e637bccd14a5130d91f934bcd26fca0aa2e34b4849e34c39243ca5cb82fa
- 07b2cd3eb58af6fb214f7cbe7c5e8c7514a6ec18: discovery 5648fc42e3850c72214630e58dc6a4c55b4fedfa0264923dddcdf12cb69605b4, T-24h 8bbf3b74c135087efedf0e6acce8b7119136716309ab91eacb3100641f9e6c1d, cut 55589eb516b0da57d006bb6d1ea705923e2ce7a8d2ad337a1ea8ad4891fb26f7
- 09b4b1a55b515bfda7331f04464115247876523b: discovery 5648fc42e3850c72214630e58dc6a4c55b4fedfa0264923dddcdf12cb69605b4, T-24h 366b725afccda7b676a7c8d15adb42f60f53e86b131f60a9efde567bd7dc9c7a, cut 0e000e25ec6abda1dde6246fad106310b2ebbe3bc35e57ba55f9d80765629c5d
- 2314e25c013df838735e9c8837afd0ff8f96f8ba: discovery 5648fc42e3850c72214630e58dc6a4c55b4fedfa0264923dddcdf12cb69605b4, T-24h 681d7c3a3dde2bed1a702cd12e1767a4242a482fc1c938825b2d86b4ef476975, cut b8a464887690e118e0c2cb94f7679d0819e438eda7c20508f3f76554dbf536e5
- 1577e767b43571e7f384566f2efcb4736b373d0a: discovery c637c6a510262d07393e221d1e0c5b09d6b66074172fffc07251fc4b3dad7e2d, T-24h 12af4f89c3197dc8f76f5d129f344efece18d6932403e58af63ed6281f442d35, cut 264bb306372d5d5119494e7f5c1b271be03d10d86bd5a757f871467aeb07ce2f
- c89dd75dab2ed2584decb2905b328483749c871b: discovery c637c6a510262d07393e221d1e0c5b09d6b66074172fffc07251fc4b3dad7e2d, T-24h cf6fa4270e3d79e07ac97c3d198a7829266778b6002b3d9972bdf73fffa638be, cut 01070b0a289b7462623f673c073f4cc2130277dfbfcdc0d075e9f702f75fcbc2
- 48f7fb4be7524ed77967d65c96d62bcde68484d7: discovery c1c42e27a772b06cfc2cf3ec40efb66df058b147ea30497c9c7cdd7bb20dc4e5, T-24h 1eb7d98b376b1733e9388a45a270863a0d44877c0a3a5baefa91382fe5988129, cut 0ec23764ccbea45acefa7a2c40b9b601fec22495dd0aa5a397d99cb5516eca88
- 87a5636549fea2fcdfb8eb0794937dcddcfe34a8: discovery c1c42e27a772b06cfc2cf3ec40efb66df058b147ea30497c9c7cdd7bb20dc4e5, T-24h 057c29f54e867e2b68ce081013c9a3cd90c8bf990214cf8a769f1ccfda0b6a9d, cut 118251e47cc18706efec70ff9f08a1d7ad902ea9dcaf7881937fb208572b86c8
- 19339dd6f111049457bbfe7762252f2b11c92762: discovery 9fb73a273ba9a71079658481de0e35a0f58703ece7893c2149eeded62a436c15, T-24h 2b1fd2c99b1fe4c2c7cf1d51073377aa1ba0d1bef0a6cf879d403c8d6d5bbca7, cut eb31da442ca61ed6ec245530a324bf42f2b4d2e3cae8944f9081c97028e7ef7c
- dfc9bdd463fa4468c8dd4ca0ce933498e10972b5: discovery 9fb73a273ba9a71079658481de0e35a0f58703ece7893c2149eeded62a436c15, T-24h a4cff7aaaa5aa7e46ed6492acbe649e0770a9cb15ad3d413e67495b7c57bbb48, cut c6679ea147007b255ab82936e75b0d7e96617b1bd3c2845191110acf0ac3cfc8
- 28e8a95eb5f9958939394587f1898b0cddbf5af2: discovery e77ae666ee69823bbd0147e30ad9937055917d16a0d29e49693bb3e6df9d7e1e, T-24h 5ef7613487817ce51042638d60d921494936f2fcaecb1198377c3231b9611944, cut feeec2cf32b9e5ddd3132f7e6a55cc3e2066f39fcc684ad4da8fcf7d9a14e765
- 656dbd30177680b8e3355c4331811a00183167d5: discovery e77ae666ee69823bbd0147e30ad9937055917d16a0d29e49693bb3e6df9d7e1e, T-24h fd94c78105a6c73135ee61fbfa00f7c2862b53306f42cc765b3af157b3c120fd, cut 54d6bf401cdd5360d8db2e782486a2b5bac9e3685d7dbd2dc0fa63ad1751a2be
- 5582b144a137dd2bbb456e551c71ee4f3d8eeef8: discovery edfd7fad62d095ddb5cd208e6b22373880fa8ddd4489e6f07cf84e45d52ae505, T-24h 43aff5b3c3c4daf0ef4f90d2be11fc94e4b9eab51d25337d524bbe497c4eb599, cut fea4c10ca7f2afa8a55469af6aff0196215aec78c57b089500c9891d4a8e8f5e
- 2f8db8bff87a32fda664261970f571fcd24aba04: discovery 5b1821159fd271fa069afc6c3e388ccc6c9aba6028c1b7784b43a237c18bb503, T-24h a6ebb3a8d77178e9974573a7415a19e460b558e6217a9d1ea33ab277060d3001, cut bb733a7fbf904bae5343b999467e5dc358c33b8d037128ed3cd24c7f9965d020
- 65d4802b2d55c386aa9ed94f9a5448077b8b9b9e: discovery 4201aa60d7a2286f656a311d8cc58dd87290c9b8c0d7d2c7d3eab014b77bd14d, T-24h a39f1b8d03f26df157d7e42c295019c57705682e6fa7f4628255a8b671024bac, cut ed5561960f802f0dd384b6195819e1df92696b538d977a938517d19490cccabb
- b5af38d56ee8f62cab7395369eccc46959e21463: discovery 4201aa60d7a2286f656a311d8cc58dd87290c9b8c0d7d2c7d3eab014b77bd14d, T-24h c4e43eeb5af73272ba01bffbd85d305559da12cb2da4c08126c90850d29cbe61, cut a0d5a7e6eae908b90808ea809b864a4d910b306a8eca96f60f6720d8b3e497f6
- 6e1db0d5c7ec7f91e6ac18b9747f61c8baa91a08: discovery e4bb342f1457716db66c855ec7a5f06718c22fe5568b794ce39e650262dd2136, T-24h 448aa40f1739b38374e5391bdf3e88290a3b2147a59fb3295c7904acbe5fd6fe, cut 42844387b8d7c9e64f21ddf91671fcf07396b6c8b94203a4987bd363b35942a6
- 5421361b86387ae39b7efbb065b535cd5c22f13f: discovery dcea5f1398dcb5b04e7a0998385d8e4dc7a504b8fcdaa1041b133ebdb19d4cec, T-24h 31ae58197b201b7416da1568cf44ad9100de6faa6e72fef89aab463cc2a5f2c5, cut 679ee2026eb290ccf32ac37df062e42ec96732fce1b7d699002e8786f884f88a
- 2fcaa8d209c2f3131e95300773a4da37d7654595: discovery 74fdb5539712e7130ded5249359eb76dcd41634f6d21ff6d88b3d3317fc5d73b, T-24h 0fae2bfbda76871d9f868f686121a230638cea3160f49528ba3a1a9d88a249fb, cut d2140831a7320cc7dd85f8ca1e8f73628674df11f2cf6727d8c65a46de3ef49d
- dbfe50ab1e90800d787062477c9f094b010ab1b7: discovery 72aaf29c8930a7cbe49e3eaed7f17ee8fe42c732db32d4c77b9907a2346974a5, T-24h 8c7d4aa924c70bb4b79c0ff33c643682dab0eaef0b9dbf89626b2274ec135f7c, cut 0a233a4cf5ff21890a090cb9568ea7fdcf7d76754e6fc0422e39cb2e7168471c
- 10f027b6018b083cbf5e1df3c2563194b12c11ae: discovery 0c7afaec71384642a163661ac45f8483b70c9a33eec78aee07f2c906197234db, T-24h 03278990510d2a5a6401dbfa14e906ce35ba99301b6103abb294a50472e34999, cut 73c4d34d03fb5fa10a2f7418f5c166126e04efec3d983d25d889c1039337ee23
- 16a6ddcf0a0b5bc975aaaa756a866317869bfc4e: discovery 0c7afaec71384642a163661ac45f8483b70c9a33eec78aee07f2c906197234db, T-24h 0e40dd833eb209a1bd9bd31f9209f73ac26395dcea6336f594a8aa2d812e300a, cut 1b0e11116958a7586e816469af028028024929afce2e453bbb4724b801751ea5
- 247bbe44296829cc888b7fc64e1ae14f3d514bc6: discovery 0c7afaec71384642a163661ac45f8483b70c9a33eec78aee07f2c906197234db, T-24h 390e19d62c4a8c81e50cce3bd6a5500b70d94db80d414982017a9f4b8a0361af, cut 586e8499156f9357b10c4b7fcf9a5b8c269dfc2a5d171bcd46bcb36ab32894e3
- 9eb09fab21f56d2508b33c6ee17e4a3767bab8a4: discovery 8d8bb25f82eeb89ea7fe4b21764f03d3e80eaeebfa924b97ea74e55cadc2dc43, T-24h 1f15ac17c09f69cc60d65ce014277ca3a5df3671dabe5187fbaf25870f8ffc1e, cut 56f0de721fd33c047b33e1ff2b5e850fae357bb8fa5f3be4c07130f4b0b89261
- b303822468d079eddf9ec17d2dae9b4c6b0e9f3d: discovery 8d8bb25f82eeb89ea7fe4b21764f03d3e80eaeebfa924b97ea74e55cadc2dc43, T-24h c5be93f79dd43c79faae14d1733a64b44b6b0b7b7288098b26ca9e6fd8d47a53, cut 87c039f7e87e8a053911dabc6cb23fa6085a8773014645dd53469d8277b83657
- e59a9794cc5fbd094606aca6c5186fe5fbbf51c0: discovery 8d8bb25f82eeb89ea7fe4b21764f03d3e80eaeebfa924b97ea74e55cadc2dc43, T-24h be2729261e7dca9d8c6f206e04c0095d1f1ffdf58ee8756181982fc6cd366e6d, cut a1631ca268fae2d1d5bb731d19371607eeb00c706e58794d3acd938045011e5b
- 235ebc6419484d76971a129475a8de6b51a3f629: discovery 0d2e3355467da6042a8c2d01271e633ed8eb9ec779d71832acec851832204d69, T-24h 65052d23f1fb2bc198b4419853748dfe527d9c1ce46539ea8b33a434b5e28104, cut e3be4098e5e7aa641bbd4089e595087b345776841e5c0b0edbb07ddb03fe2189
- 9ac5de066dc46c5e3119b92da4bfd2c19fa48341: discovery 0d2e3355467da6042a8c2d01271e633ed8eb9ec779d71832acec851832204d69, T-24h c23bc9350d7d6178ad59f5ff898e36c94b3f03ab68b32e6b412037fa0381d7f4, cut a0a13e9f738b9e1da10bbfb0c0493220a47bcfc036f4dd582cbd15ae7b007f00
- c98935063f4cddc173db29fc06c354ebeb8b089f: discovery 0d2e3355467da6042a8c2d01271e633ed8eb9ec779d71832acec851832204d69, T-24h 97b311110b25f15643e07ba24063275c9b943de830aa325a4ffcd92752364bf0, cut c8933bfd2f539301f31377683c38254462c67faabeb290c1e4c00e9b39a3ac9c
- 31981f0f9cf388be5b37d76f46ebcc201684e777: discovery af588a3ffc249e71760aa53fa1d774c84744b0bbe4ee187a037fb90d18bc6da9, T-24h f3121274c43c8001bc9ce751fc6a81b979c5c29ab2784cbd856d6c1c1552784d, cut 7d3210233cad49b316d937b09da69d0b6d5cc601bedc8be8ad15a03370d2de6b
- 5fe0d3392322abc41e6464a75d1c7511b63d286e: discovery af588a3ffc249e71760aa53fa1d774c84744b0bbe4ee187a037fb90d18bc6da9, T-24h 412ea803443deff5e283447d4d9fa9c271c715f86a853b7d1c1167b4a6ccdfd2, cut 515edf7285b79d9969781c0c340a0ed84b032e6d1f97cb9e66ab7d973a521aa4
- 2d5ee459298e21ead2d11cd777c60e3e3ae63058: discovery d878af464dfc46b5a99f8813fa4b91163bf58a9c00b2ce95177e79175aa225f4, T-24h bd3ade1b90498a50f9c6d7a6e311e13cf0c46b93ad6ddb90ab2bff55a3f9e6db, cut be1006cec21962f46f0871f04e9698e3fe91a951ac93857b75cb5e3e0ecb161b
- 43da5d417823809ccdf6705b7f878273cf468724: discovery d878af464dfc46b5a99f8813fa4b91163bf58a9c00b2ce95177e79175aa225f4, T-24h 77d15204dcef9f434ea70f08d528109366d0e3a4b569a5da70ebec4be79541e0, cut 6987333071bc252490798d10663b920f24c3fec1f066ee475b54e28833937cc4
- 4b9975d792f2e3865b0391677fd04b8dcdfc34e1: discovery d878af464dfc46b5a99f8813fa4b91163bf58a9c00b2ce95177e79175aa225f4, T-24h aad47b85402bdd1c8879d264bbb93211f4245c3584ea97720fbaa5ec3ff33b32, cut 4faabd4e1bc123701c91e961fd16e3bf57336a0f24eebcc0b1a001602bf4f0f3
- 537d77ba1e0dbc812d44c73dae97ef1ae35ca8e0: discovery 76d798f7a0c0a0f151950a0f46b14cf6f634c476bb25c253b519efe956f204fa, T-24h 47d8c057f5c1ece1e932628db453ed3ae1af636e2fc192a94301db5e694a603e, cut 881ba02c00f4593ae7b361119aefac806380d8b08c210cdcdbac600e87563947
- 725f96b1bc51729c9963f14cde849a2756517aa2: discovery 76d798f7a0c0a0f151950a0f46b14cf6f634c476bb25c253b519efe956f204fa, T-24h eb960fe1ebdcd9b7c54c17214097bc93ffabcd9271ebdc322df983141351f708, cut 44aa3f1462a1bb57744cda246bcafc3165895d95f217169ae4a0c7f2201c3e45
- f6c6bfd08129cff9f57d98d7d06b9cc18b5539c5: discovery 76d798f7a0c0a0f151950a0f46b14cf6f634c476bb25c253b519efe956f204fa, T-24h d122171028acd5cb456f9038f58a970df865dabf75130441e884c910ee46a658, cut baa0f83410cf9b226934b275cb932693715c4cb77ad6d82bc61e8d2ac8b68db0
- 671ddacdfb72347daf1770be52c5c65391e6032e: discovery c643ab07421488a3cea1bcd13b3e83e2b68afa8a4a4c8350c6bf3a74748eb8a9, T-24h 02020d270c1be369ff5975133a02146804fe3e8bbea8a287661b5bd36809c645, cut 2b2bf8b28bcd08e4d02de3cc94263fac340d2125d99c17573c1742ffc8f7af12
- f3b3551ac420566fc35b840e5570cef1a5721dbb: discovery c643ab07421488a3cea1bcd13b3e83e2b68afa8a4a4c8350c6bf3a74748eb8a9, T-24h 555c6cb42d3f4403beb566f981195d95ab3024db50d6e587b83c2eb44131c95c, cut c78ec22763393fafbb639cbd3246453bd71d90fe89ab9856bc467c3980527e07
- fe672c9c8ac1f2e30d7625c5470e18b6a5b6e22d: discovery c643ab07421488a3cea1bcd13b3e83e2b68afa8a4a4c8350c6bf3a74748eb8a9, T-24h 481c012532ce5134f75b9b9fb5af9a42f18d83da4794deec25313557fcc34c5d, cut 7edddbe84f9b87ab8564503b0cf55caa3e9630257fb762953ee812f8c5b3b8d0
- 7665678b0d016066a30d6fd1f521f3b18e0eb3b8: discovery d73582ec792af47663d062c46ee54116373923336d5d1b038cc201fd0d0bc59b, T-24h 42c2bf4feb991b63c9f9631fbdedbc086482fa729d8fb9b106c22f0f068ccd6c, cut 3e289c82aa137e5753c54bc3416c24295d390327746295a70ece49e735b63bd5
- 7d129084695a5bcd19a0cbdbc9b06949c470e06b: discovery d73582ec792af47663d062c46ee54116373923336d5d1b038cc201fd0d0bc59b, T-24h 0ac468f22c255d7118c6aede87631050aea7d67749ad6edab2d5a81fec3513b8, cut 74ddb3a10c13e533b055f509985af6bb672f8896ae68bd066db073a076491cdc
- b803f4c56d91898211cd6760465a8d54ca6dd3d1: discovery d73582ec792af47663d062c46ee54116373923336d5d1b038cc201fd0d0bc59b, T-24h 98e9fdd1b445ced83fbc24620aad1bfa0358b1ec456f3fa542f12f12611f738d, cut 40e056b1f2835c6ee25cf58a390468a07dd2d613e7c0f74b6f5766b349be6051
- 0cb73ea6d8ea5de29533060a0f1568b30fb17d39: discovery a3d22b99856eb349c49e252690ec021af917b98df4262b0521dfd3c0b4d750cb, T-24h 59e1a3ad6d098ec73b74bf7a3d4a532f43d23346a8558ae9ccba9a1954ebf5c8, cut 27779179d3383ec209d4d7935088db1ed8bba42e0bb6a97cf2141417012939b6
- c90af508f989723e3e62d6c358d691a7fc0360db: discovery a3d22b99856eb349c49e252690ec021af917b98df4262b0521dfd3c0b4d750cb, T-24h bf389719b098557609c9f4e8923e33b5077179be0db98fefcaf9591737bd2c22, cut 2be510380bf49806a51e5f851030643aa6e84c4cf6287b960730e75c95bbbb65
- 3dbd05bde385537c8312f6cdfc87627e43493b6d: discovery 432a6fa4588eecf4b6d182da99a09f9f20c4e709ddfd2072e01a6438c156f48d, T-24h cf664bb11c25cad40ebfaef73d3eaeb8308321db2015e72a3854a9d0dd4f730a, cut 73967c12e1c2027cadd2dea2965d98b411a0fbfd1fc1eb8316fe3a676f3bc832
- 5fa05540308d97c2a34328df1e9b92deb05593e4: discovery 432a6fa4588eecf4b6d182da99a09f9f20c4e709ddfd2072e01a6438c156f48d, T-24h 65bb29eaad2c13acab2fcc01ae6d6c7d45d6920722cb182f42f7136e8e72f30f, cut a96b9cf87a3b4bcb9bd7a38ca859805b0dcc9fff067a03a081b16c3b8daa3ec0
- 003fb0bc9df59903463cd53adfafb8cdefc8c975: discovery 41e608a5db0576b393c70366095f1c195a183a387d57c02258de9ac3dca47b97, T-24h da70960b86fa59a5c6953cd848312735f8da4d7d0eb7d929933fd16e33dc2423, cut ae6989e1bdcb2ca8e775cc6878860edfa15b0ff8c9691ce8c62ce80a8569854f
- 2e73d8254ae0f5c5982807c7097645f7696b197a: discovery 41e608a5db0576b393c70366095f1c195a183a387d57c02258de9ac3dca47b97, T-24h 381f7dac9e2bc459afe36ec1106d4fdbb2f1ded3a807fbf013a845d8a7123119, cut 5812ea0b79b88fe856b9072258134e291ff1ed968592b6e494eb81a68f3e45de
- 6f3f5c5652f429b973b11fd97c06af0fa9864943: discovery 41e608a5db0576b393c70366095f1c195a183a387d57c02258de9ac3dca47b97, T-24h ecffa56aff14239f742509319f118dd67494a66c5fff4780fa79a1f791d87be1, cut e5e582a4402ad2fe14d733316eb8bc23f58f2cd7e18cc965aa333ca4e9492061
- f30ad85ed231d345a58d98da35817c57ac3ec78d: discovery 41e608a5db0576b393c70366095f1c195a183a387d57c02258de9ac3dca47b97, T-24h 4f46dfed974c48978da25739a88ce07067bccbb862d804d869472a64d8ab387f, cut e7416ab9089a7693149f33ab9ec95d0d6fda53134535819aba27900bcbc53a6c
- 505a81990ccb7a0ba3f5411d8d5f8af2d414c90b: discovery 67a1e1bd76e44330a6910d0af1b028418f8ecf754824e448d399cecb8bb49dd7, T-24h b0012098c57a58991e197f401025f51839c7981e65d6792e0f3a542b0f45aa48, cut e3fe8c12d3cb7a6bfe256c43e2f6e0967accc3bfe5d5fe0a55b1e4a76d6c92fd
- 573a91bb3e65d8bc1576a531618ecfa0fe87da86: discovery 67a1e1bd76e44330a6910d0af1b028418f8ecf754824e448d399cecb8bb49dd7, T-24h 715acc5bc793c6222786a4b4a428b1ed0604197779f418c9d32193c6ec26a9de, cut 5dd4ba8742e1a393117317c5107f1258beed22bc48e9bd82d066eed1ef4e2094
- 8427fe99e7ba57c3b9eb5b18bff4d42f12eb4124: discovery 67a1e1bd76e44330a6910d0af1b028418f8ecf754824e448d399cecb8bb49dd7, T-24h d7704613f225f1052fd43e72dacdd9c20dcb31e5ab07a33ad2fdbbccd9f01641, cut b030a5e5547f7d0082ac4f2f207c7630c8be9ecbd6ea93871e8373fb36277839
- 9c49f928758ed1a302d96d5de24732477cb2b899: discovery 67a1e1bd76e44330a6910d0af1b028418f8ecf754824e448d399cecb8bb49dd7, T-24h 05d04740a2ee7250616ed9688a6552689a17679d1ce33a654b10145c4d30c06e, cut 3382ee24efe715336666f762643f4e0371d29cbef90df0ba5d55b30905687031
- 5f90fdd5c676639cd679b4db2c5be9bf150de105: discovery 8414a20946eea52d91cef0a7712f3a182516b2a26e58d3d093f6293703849c92, T-24h 27522a4e365ea16cd6c3e246b786ef9ae37675e4a7cefdcac453fd1322ab957f, cut f6f0a4bd212494ae47ef747a158db56ffc65595552fa2f9387e9fb317d12839b
- cf38d00e867ea0f934c34f515a129a52b83a4429: discovery 8414a20946eea52d91cef0a7712f3a182516b2a26e58d3d093f6293703849c92, T-24h e409d7e40496e69dd565a0421d84bd393d174b89715dbf9b73d4ee1715a9474f, cut eb616ab132f1b54f927d6dd0e9bae86202a337a4b7b25f39bf0f4f7a80cf68a9
- 363ebf8128a2df8fa4a280dd90f48c7849c88d17: discovery 1b7f8d9a351ab797859b9b3f060ee920a7b58d7d8bd6ee79bf53c6f3d5c34334, T-24h 4644822495a1d509d48c779d76627ee4aa10e4a20a969286be87aa70b6ccdfd1, cut 1d954fffcc754cdf555e5243236a220be4685ea08330271933924cd5bb21472d
- f35b51ac0d37da79fea2d654ed11138a9e28f2a2: discovery 1b7f8d9a351ab797859b9b3f060ee920a7b58d7d8bd6ee79bf53c6f3d5c34334, T-24h cf93725a0d5c69c5021a32c0fc39f37051b51616484b5e30778382bc1713a029, cut 17f6b4bfb951a98011d8aa0c3a1cc69b74b0bfcd8436a7dbbe977ed3d91bb9e9
- 1d8e567ee94309c870d2f57a40f4cd14b3056ff4: discovery 8447b5796cefa82955d64545e5d2ffdfc73ea102148a196018c6443ae736d707, T-24h e5be6705255353f08ba819ddc06120b29bbd0381fee0757887e416c9065efa21, cut 24f473dd69834e58d4163bf700f8798fe809ca042ac7638aa4f19bd92eee535a
- 4499ff0633b3dc23dac87133f4a5bef832524828: discovery 8447b5796cefa82955d64545e5d2ffdfc73ea102148a196018c6443ae736d707, T-24h c8c73ba396c07b343bc8ce9e4f7a58395990d3b5d55e6591cd9e59fe380870df, cut e9d62b9bd7fc91b84225c946e23ebd22df056a7c771dadfcb3472d5e24595e45
- 6241bc8e4fa8fbe15bb3855dd8db2901f054efb8: discovery dba905d9ff38dff96701736eef60fdf4855967ee9dc318203fae7751b993cb3e, T-24h 3346a963b105478e53806d64a4d31d62d6f163da42b65050abb1cecd4a547210, cut ae1b7c534f009dfdb0ea4156c0cb82aef20ca953834cfdd6dd4d29b16e0f4e4e
- fb84dd9c32c6943b68bc59b8836869364dfb5721: discovery dba905d9ff38dff96701736eef60fdf4855967ee9dc318203fae7751b993cb3e, T-24h 5eac1511d1965900f9d7fd59461934783aef0f99f563218312519e7d0810bc18, cut 528056f9ce7b09591d96885ee34f2a63bca401c7fb8a4fc6414b3db1a510c35a
- 096b8e5a232755e93143e987081de9b0675bebd3: discovery f5c03e573ab1681d0d0030ae9c52d13467569f982a8a4f50d51762fb691e2a65, T-24h d4696c965675d1d781c5f8fd1833545cb8cceb54144504dff020753814aac8fe, cut 9dc0b6eb3fda5e9a13a16b99c14c43b21225dd223558e4b47067e70cecd9d334
- 5d3a11a88e8cd9c0cb6141251c3d838153fdc388: discovery f5c03e573ab1681d0d0030ae9c52d13467569f982a8a4f50d51762fb691e2a65, T-24h b53b032d4881506fa0b36ccfc54f797bcab7f98f603ef21429dd8c327f104588, cut 9a1596236398975f49cb5b052ebe718e0abf0775a5acc42766a42a9611ecad68
- 2b26fc979d5c804bd5d4f88fc5e0db1cebaae219: discovery 498c2a45770e1c156eb1f20729731f491eeb10ae87ea4b4b17bba7a00a9202e1, T-24h 4f13e2508920275fe4d56be23d7d70f660bedf352d1fe016837706a8802c1491, cut 2af93c765137446023a08677702764485302630a10349796d4d405e365799999
- 878c3b301b56c2d579811219552f0770f2265cd7: discovery 498c2a45770e1c156eb1f20729731f491eeb10ae87ea4b4b17bba7a00a9202e1, T-24h f1de0eb8125911a8dde968c5d038f1d1eee3d08f80a52e1eb1c73c43a83d4e21, cut 1ceedbb0bb2c81dd25b7ab64360c721660d1165a2d4b3ebcf798c4835b1c479e
- b0d16b11d42f505eef130ec5a3f561d4cc7afecc: discovery c7ad2365d4a1f24e8ed8470a86e547de5985183e4630cefe076d37d87b656280, T-24h 118167898c6a70c6bdd56cf07fa4028fe8605f70eca4a421b851ec5d4b2b0319, cut 0b2c1289898f908798f01326db7063b785697e1b0bb398b99bd5ca029470105d
- c7da8aaec7ff3a2ad59161d8a8a271d2b4b49c57: discovery ddbc503e8b321dca089696dac2f7f6e1f240884af02c34495c63555a58a632ed, T-24h 225bb5802d1c471bb3c8e76e194f73f31844315364b405e0dc66ede3caa95e64, cut 2f83ae5bb224b2eccb9362c8def60005e38e76619fcf877307908a54bead793a
- e0e064266b116a0d4d63b48fc81591da151f638d: discovery a080c518659202f40f47f6ae67db235ca01ac75373bcbb7e7625678d85f2a17b, T-24h 5bb01e194167c094fa16cd376c71bf231d8a3cb1889a6b71d99d33ec1d26b938, cut 9ed7a3fad34129c0d1254facb6b15560a42c920f8914099de424477ce6f65673

## Actual usage (`x-requests-last` / `x-requests-used` / `x-requests-remaining` headers)

| call | path | x-requests-last | x-requests-used | x-requests-remaining |
|---|---|---|---|---|
| 1 | `/v4/historical/sports/soccer_fifa_world_cup/events/d1f4f946c70a0b4e81f5d43e9d32361c/odds` | 10 | 4392 | 15608 |
| 2 | `/v4/historical/sports/soccer_fifa_world_cup/events/d1f4f946c70a0b4e81f5d43e9d32361c/odds` | 10 | 4402 | 15598 |
| 3 | `/v4/historical/sports/soccer_fifa_world_cup/events/289bc2e9f5adad8ae4d9a75a7c5461ad/odds` | 10 | 4412 | 15588 |
| 4 | `/v4/historical/sports/soccer_fifa_world_cup/events/289bc2e9f5adad8ae4d9a75a7c5461ad/odds` | 10 | 4422 | 15578 |
| 5 | `/v4/historical/sports/soccer_fifa_world_cup/events/512ac18beb5aa936a59f7ea3e497ada2/odds` | 10 | 4432 | 15568 |
| 6 | `/v4/historical/sports/soccer_fifa_world_cup/events/512ac18beb5aa936a59f7ea3e497ada2/odds` | 10 | 4442 | 15558 |
| 7 | `/v4/historical/sports/soccer_fifa_world_cup/events/9eeb4876001f5a52ce3c3641bd5f1f2f/odds` | 10 | 4452 | 15548 |
| 8 | `/v4/historical/sports/soccer_fifa_world_cup/events/9eeb4876001f5a52ce3c3641bd5f1f2f/odds` | 10 | 4462 | 15538 |

Store rows rebuilt from receipts: 23787.
