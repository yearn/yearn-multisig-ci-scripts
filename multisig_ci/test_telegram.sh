export TELEGRAM_MESSAGE=$(cat << EOF
✍️ [eth #196](https://gnosis-safe.io/app/eth:0x7d2aB9CA511EBD6F03971Fb417d3492aA82513f0/transactions/queue)
Sender: milkyklim (via cronjob or manual trigger)
Description: Recycle SPELL into yvBOOST which is sent to donatooor
Function ran: buy_yvboost_with_spell in scheduled.py
Verify [the output](https://github.com/yearn/ytrades-ms/actions/runs/2270768787), and [sign here](https://gnosis-safe.io/app/eth:0x7d2aB9CA511EBD6F03971Fb417d3492aA82513f0/transactions/queue)
EOF
)
echo "TELEGRAM_MESSAGE<<EOF" 
echo "$TELEGRAM_MESSAGE"


token="1849087300:AAGrr8_HblI9yDLzGrp4MOuwzrA-go1BmKk"
chat_id="-1001730863656"
python3 telegram.py send_and_pin_message $token $chat_id