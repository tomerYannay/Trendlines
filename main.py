from daily import daily_update
from db import updateDBWithAPI, dump_profile_csv
from scripts.compute_betas import compute_and_store_betas

# from tests import d_check_and_update_upper_trendline, d_update_upper_status
# from tests import log_positions_for_stock

try:
    daily_update()
finally:
    dump_profile_csv("profile_times.csv")

# compute_and_store_betas()
# from tests import d_find_and_update_upper_trendline, d_update_all_upper_trendlines, d_update_upper_status, \
#     d_check_and_update_upper_trendline

# # d_find_and_update_upper_trendline('AAPL', '2010-01-08')
# # d_update_all_upper_trendlines('AAPL', '2010-01-08')
# d_update_upper_status('AAPL', '2010-01-08')
# d_check_and_update_upper_trendline('AAPL', '2010-01-08')

# tickers = ['MMM', 'AOS', 'ABT', 'ABBV', 'ACN','ADBE','AMD','AES','AFL','A','APD','ABNB','AKAM','ALB','ARE',
#                    'ALGN','ALLE','LNT','ALL','GOOGL','MO','AMZN','AMCR','AEE','AEP','AXP','AIG',
#                    'AMT','AWK','AMP','AME','AMGN','APH','ADI','ANSS','AON','APA',
#                    'APO','AMAT','APTV','ACGL','ADM','ANET','AJG','AIZ','T',
#                    'ATO','ADSK','ADP','AZO','AVB','AVY','AXON','BKR','BALL','BAC','BAX']
#
# for ticker in tickers:
#     try:
#         log_positions_for_stock(ticker)
#     except:
#         continue
#

