import dash
import dash_html_components as html
import urllib.parse as url
import requests
import pandas as pd
import logging
import os
import numpy as np
from flask_caching import Cache

URL = os.getenv('SITE_ROOT', "/")
USER = os.getenv('JIRA_USER')
PASSWORD = os.getenv('JIRA_PASSWORD')

# get from env?
# allow to tweak in page?
JIRA_URL='https://matsim.atlassian.net/'
JQL='project = MATSIM AND labels = DevMtg2018 ORDER BY votes DESC, Rank ASC'

SEARCH_URL=JIRA_URL + 'rest/api/2/search?jql=' + url.quote(JQL)

app = dash.Dash(__name__, url_base_pathname=URL)

# Setup Redis caching.
cache = Cache()
CACHE_CONFIG = {
    'CACHE_TYPE': 'redis',
    # Keep data cached for 1 minute.
    'CACHE_DEFAULT_TIMEOUT': os.getenv('REDIS_CACHE_DEFAULT_TIMEOUT', 60),
    'CACHE_KEY_PREFIX': 'dash_',
    'CACHE_REDIS_HOST': 'redis',
    'CACHE_REDIS_PORT': 6379,
    'CACHE_REDIS_DB': 1,
    'CACHE_REDIS_URL': 'redis://redis:6379/1'}
cache.init_app(app.server, config=CACHE_CONFIG)


@cache.memoize()
def get_interest():
    search_response = requests.get(SEARCH_URL,auth=(USER, PASSWORD))

    if search_response.status_code != 200:
        return html.Div('JIRA query failed with status {}'.format(search_response.status_code))

    votes = [(issue['key'] + ' ' + issue['fields']['summary'],
              voter['displayName']) for issue in search_response.json()['issues']
         for voter in requests.get(issue['fields']['votes']['self'], auth=(USER, PASSWORD)).json()['voters'] ]

    df = pd.DataFrame(index=pd.Series([issue for (issue, voter) in votes]).drop_duplicates(),
                      columns=pd.Series([voter for (issue, voter) in votes]).drop_duplicates())

    for (issue, voter) in votes:
        # check how to do that
        df[voter][issue] = 1

    # order by number of votes
    return df.assign(interest = lambda df: df.sum(axis=1))\
            .sort_values(by='interest', ascending=False)


def tick(marker):
    if np.isnan(marker):
        return html.Td()

    return html.Td(html.I(className="fa fa-smile-o fa-2x"))


def issue_link(description):
    key = description.split(' ')[0]

    return html.Td(html.A(href=JIRA_URL+'browse/'+key, children=description))

def serve_layout():
    df = get_interest()

    return html.Div(children=
        # Headers
        [html.Tr([html.Th('Issue')] + [html.Th(col) for col in df.columns])] +

        #Body
        [html.Tr([issue_link(issue)] + [
            # TODO: instead of displaying value, make a color box if not NaN
            html.Td(tick(df[voter][issue])) for voter in df.columns[:-1]
        ] + [
            html.Td(df['interest'][issue])
        ]) for issue in df.index]
    )


app.layout = serve_layout

app.css.append_css({
    "external_url": "https://codepen.io/chriddyp/pen/bWLwgP.css"
})
app.css.append_css({
    "external_url": "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css"
})

if __name__ == '__main__':
    app.run_server(host='0.0.0.0', debug=True)
else:
    # make Flask log messages visible on the console when running through gunicorn
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.server.logger.handlers = gunicorn_logger.handlers
    app.server.logger.setLevel(gunicorn_logger.level)

    # To make server understand the "Forwarded" header set by nginx when serving the app somewhere else than the root.
    # Otherwise, the app does not manage to link to other parts of itself and crashes.
    # app.server.wsgi_app = ProxyFix(app.server.wsgi_app)