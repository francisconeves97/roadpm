# - coding: utf-8 --
"""
@info webpage to find patterns in traffic data
@author Francisco Neves
"""

import dash
import dash_core_components as dcc
import dash_html_components as html
from dash.dependencies import Input, Output
import os
import pandas as pd
import json

from app import app
import gui_utils
from roadpm import method_parameters, biclustering_handler, get_multidrop_options
from roadpm_utils import get_biclustering_vis


def get_all_method_params():
    params = [method_parameters[method] for method in method_parameters]
    res = []
    for param_list in params:
        res += param_list
    return res


DOWNLOADS_PATH = str(os.path.abspath(os.path.dirname(__file__))) + '/data/'

pagetitle = 'Biclustering'
prefix = 'padroes_rodovia_from_file'

parameters = [
    ('nan', '10', gui_utils.Button.input_hidden),
    ('csv_file_upload', '', gui_utils.Button.upload),
    ('csv_file_path', '', gui_utils.Button.input_hidden),
    ('method', 'biclustering', gui_utils.Button.input_hidden),
    ('dataset', ['waze', 'espiras', 'integrative'], gui_utils.Button.radio),
    ('attributes', [''], gui_utils.Button.multidrop)
]
charts = [
    ('results_container', gui_utils.get_null_label(), gui_utils.Button.html, True)
]

layout = gui_utils.get_layout(pagetitle, [('parameters', 27, parameters),
                                          ('method_parameters', 27, get_all_method_params(), 'empty_box')], charts,
                              prefix=prefix)


def get_graph(fig, title=None):
    children = []

    if title is not None:
        children.append(html.Div([html.H3(title, style={'marginBottom': 0})], style={'textAlign': "center"}))

    children.append(dcc.Graph(figure=fig))

    return html.Div(children)


def get_state_field(field: str, accessor: str = 'value', prefix: str = '', type=None):
    states = dash.callback_context.states
    value = states['{}{}.{}'.format(prefix, field, accessor)]
    if type:
        if type == dict:
            try:
                value = eval(value)
            except:
                return None
        else:
            value = type(value)
    return value


@app.callback(
    Output(prefix + 'biclusters_container', 'children'),
    [Input(prefix + 'biclusters', 'value'), Input(prefix + 'biclusters_cache', 'value'),
     Input(prefix + 'biclusters_plot', 'value')])
def show_bicluster_plot(sel_bics, bics, plot_type, *args):
    if bics == '':
        return ''
    bics = json.loads(bics)

    figs = []
    for bic_i in sel_bics:
        if bic_i == 'no_biclusters_available_yet':
            break
        bic = bics[int(bic_i) - 1]
        fig = get_biclustering_vis(bic, plot_type)
        figs.append(get_graph(fig, 'Bicluster {} - pvalue {:.4g}'.format(bic_i, float(bic['pvalue']))))
    return figs


@app.callback(
    Output(prefix + 'method_parameters', 'children'),
    [Input(prefix + 'method', 'value')])
def change_method(abordagem, *args):
    res = []
    for method in method_parameters:
        params = method_parameters[method]
        if method.startswith(abordagem):
            title = method.replace('_', ' ').capitalize() + ' Parameters'
            children = gui_utils.get_block_parameters(method + 'method_parameters', title, 27, params,
                                                      prefix=prefix)
        else:
            children = gui_utils.get_block_parameters(method + 'method_parameters', '', 27, params,
                                                      prefix=prefix, hidden=True)
        res.append(children)

    return res


@app.callback([Output(prefix + 'csv_file_upload_output', 'children'), Output(prefix + 'csv_file_path', 'value')],
              [Input(prefix + 'csv_file_upload', 'filename')])
def update_output(csv_file, *args):
    if csv_file is None or len(csv_file) == 0:
        return '', ''
    return html.Span(children=csv_file), DOWNLOADS_PATH + csv_file


@app.callback(
    [Output(prefix + 'results_container', 'children'),
     Output(prefix + 'attributes', 'options'),
     Output(prefix + 'biclusters', 'options'),
     Output(prefix + 'biclusters_cache', 'value')
     ],
    [Input(prefix + 'button', 'n_clicks')],
    gui_utils.get_states(
        parameters + get_all_method_params(), False,
        prefix))
def run(n_clicks, *args):
    dataset = get_state_field('dataset', prefix=prefix, type=str)

    csv_file = get_state_field('csv_file_path', prefix=prefix, type=str)
    if csv_file == '':
        return [], [], '', ''

    state_params = dash.callback_context.states
    # remove prefix and .value from
    params = {}
    for key in state_params:
        params[key.replace(prefix, '').replace('.value', '')] = state_params[key]
    time_series_orig = pd.read_csv(csv_file, parse_dates=True, index_col=[0])
    attributes = get_state_field('attributes', prefix=prefix, type=list)

    if len(attributes) > 1 or attributes[0] != '':
        time_series = time_series_orig[attributes]
    else:
        time_series = time_series_orig

    res, bics = biclustering_handler(time_series, dataset, prefix=prefix)
    bic_options = get_multidrop_options('Bicluster {}', range(1, len(bics) + 1))
    bics_cache = json.dumps(bics)

    time_series_attrs = list(time_series_orig.columns)
    time_series_attrs = get_multidrop_options('{}', time_series_attrs)

    return res, time_series_attrs, bic_options, bics_cache


if __name__ == '__main__':
    app.layout = layout
    app.run_server(debug=False, port=8050)
