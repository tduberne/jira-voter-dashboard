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
JQL='project = MATSIM AND status in ("In Progress", Open, "To Do") AND labels = DevMtg2018 ORDER BY votes DESC, Rank ASC'

SEARCH_URL=JIRA_URL + 'rest/api/2/search?jql=' + url.quote(JQL) + "&fields=votes,reporter,summary"

app = dash.Dash(__name__, url_base_pathname=URL, csrf_protect=False)

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

    # TODO handle in a way compatible with memoization
    #if search_response.status_code != 200:
    #    return html.Div('JIRA query failed with status {}'.format(search_response.status_code))

    votes = [(issue['key'] + ' ' + issue['fields']['summary'],
              voter['displayName']) for issue in search_response.json()['issues']
         for voter in requests.get(issue['fields']['votes']['self'], auth=(USER, PASSWORD)).json()['voters'] ]

    reporters = [(issue['key'] + ' ' + issue['fields']['summary'],
                  issue['fields']['reporter']['displayName']) for issue in search_response.json()['issues']]

    df = pd.DataFrame(index=pd.Series([issue for (issue, voter) in votes] + [issue for (issue, voter) in reporters]).drop_duplicates(),
                      columns=pd.Series([voter for (issue, voter) in votes] + [reporter for (issue, reporter) in reporters]).drop_duplicates())

    for (issue, voter) in votes:
        df[voter][issue] = 'V'

    for (issue, reporter) in reporters:
        df[reporter][issue] = 'R'

    # matrix issue x issue with n persons that want in both
    m = df.notna().as_matrix() * 1
    keys = [d.split(' ')[0] for d in df.index]
    conflict_matrix = pd.DataFrame(m.dot(m.T), columns=keys, index=keys)

    # order by number of votes
    df = df \
            .T.assign(total=lambda d: d.notna().sum(1)) \
            .sort_values(by='total', ascending=False).T\
            .assign(interest = lambda df: df.apply(lambda x: x.notna()).sum(axis=1))\
            .sort_values(by='interest', ascending=False)\

    df = pd.concat([df.loc[list(df.index != 'total')], df.loc[['total']]])
    df.loc['total','interest'] = np.nan
    return df, conflict_matrix


def tick(marker):
    if marker == 'V':
        return html.Td(className="w3-green", children='V')

    if marker == 'R':
        return html.Td(className="w3-red", children='R')

    #return html.Td(html.I(className="fa fa-smile-o fa-2x"))
    return html.Td(marker)


def issue_link(description):
    key = description.split(' ')[0]

    if key == 'total':
        return html.Td('Total')

    return html.Td(html.A(href=JIRA_URL+'browse/'+key, children=description))


def serve_layout():
    df, conflict_matrix = get_interest()

    return html.Div(className="w3-container w3-responsive",
                    children=[html.Table(className="w3-table w3-striped w3-hoverable w3-bordered w3-small",
                                        children=[
                                        # Headers
                                        html.Thead([html.Tr([html.Th('Issue')] + [html.Th(col) for col in df.columns])] ),

                                        #Body
                                        html.Tbody([html.Tr([issue_link(issue)] + [
                                            # TODO: instead of displaying value, make a color box if not NaN
                                            tick(df[voter][issue]) for voter in df.columns[:-1]
                                        ] + [
                                                     html.Td(df['interest'][issue])
                                                 ]) for issue in df.index])
                                        ]),
                            html.Table(className="w3-table w3-striped w3-hoverable w3-bordered w3-small",
                                       children=[
                                        # Headers
                                        html.Thead([html.Tr([html.Th()] + [html.Th(col) for col in conflict_matrix.columns])] ),

                                        #Body
                                        html.Tbody([html.Tr([issue_link(i)] + [
                                            html.Td(conflict_matrix[i][j])
                                            for j in conflict_matrix.columns
                                        ]) for i in conflict_matrix.index ])])])


app.layout = serve_layout


app.css.append_css({
    "external_url": "https://www.w3schools.com/w3css/4/w3.css"
})
#app.css.append_css({
#    "external_url": "https://codepen.io/chriddyp/pen/bWLwgP.css"
#})
#app.css.append_css({
#    "external_url": "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css"
#})

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
