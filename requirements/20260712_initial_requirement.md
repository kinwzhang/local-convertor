This project is to achieve a local deployment of converter to convert CLash YAML, pull from remote, into a subscription list, for daede's consumption.

#### Background
Including two reference projects:
1. openwrt-daede, which offers a managing the daed instance ran on immortalwrt
2. urlclash-converter, which offers a convertion of clash yaml into the list daed can understand.

#### Project goal
1. achieve the convertion in a local deployed flask app, with front end to input multiple clash subscriptions.
2. the project should also exposure the converted subscription as a url, one subscription should have a distinct url(presistence per provider and clash link) for daed to subscript with.

The user journey should be:
1. provide a clash link to local convertor, and save it.
2. local convertor checks update about the clash link on scheudle or upon user request
3. local convertor convert subscription into a file, and provide the url pointing to the file.
4. user copy the url, and paste into daede's UI:
    - the url will be pasted when user click: /html/body/div[1]/div/div/main/div/div/div[3]/div[3]/div[1]/div[2]/div[2]/button
    - when user clicks update button, daeds should issue a query to the url, and once local converter receives the request, it should:
      - check how old the subscirption is? 
        - If more than 3 hours, it should pull the clash link, update the subscription file, then reture.
        - If less than 3 hours, it should return the file
      - update button sample(1st and 2nd subscritpions): 
        - /html/body/div[1]/div/div/main/div/div/div[3]/div[3]/div[2]/div/div[1]/div[2]/div[1]/div[2]/div[3]/button
        - /html/body/div[1]/div/div/main/div/div/div[3]/div[3]/div[2]/div/div[2]/div[2]/div[1]/div[2]/div[3]/button

Local convertor's workflow to update a clash url:
1. send the request to provider
2. once response received: compare if the raw response is identical with the previous immediate version
   - if the same, refresh the file creation time
   - if difference appears, regenerate the file, and preserver last 5 versions of the generated file, however the url link should always be pointing to the latest file.
3. set the url link pointing the latest version of file
4. always keep a copy of last five version of the file and the raw response from provider.

The UI should have the main screen for user to manage Clash links
|provider|clash link|url link|auto update|action|
|---|---|---|---|
|provider 1|clash url1|url link 1|dropdown option|update now, copy link(url link), link rotation(url link), delete,|
|provider 2|clash url2|url link 2|dropdown option|update now, copy link(url link), link rotation(url link), delete,|
||||dropdown option|save|

- Always provide a new row, once user edit, offer a save button to save the new records.
- the drop down option should allow user to set auto update frequency:
 - auto update or not
   - auto update on: once a month|week|day|hours
   - for once a month: pick on which day through the month, at what hh:mm on that day
   - for once a week: pick which weekday at what hh:mm on that day
   - for once a day: pick what hh:mm on the day
   - for once x hours: provide drop down to pick "once x hours"
- the url link, unique, should be populated once user save a row

Below the subscription list, there should be a dynamic log output box so that user know the subscirption update status.
- querying provider
- pending provider response
- receive repsonse from provider
- whether changes observed
- updating file
- subscription update finished.

