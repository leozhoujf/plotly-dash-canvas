import dash_canvas
import numpy as np
import pandas as pd
import dash
from dash.dependencies import Input, Output, State
import dash_html_components as html
import dash_core_components as dcc
from dash_canvas.components import image_upload_zone
from dash.exceptions import PreventUpdate

from dash_canvas.utils.io_utils import (image_string_to_PILImage,
                                        array_to_data_url)
from skimage import io
from dash_canvas.utils.registration import register_tiles
from dash_canvas.utils.parse_json import parse_jsonstring_line
import dash_table
from ipdb import launch_ipdb_on_exception

def tile_images(list_of_images, n_rows, n_cols):
    dtype = list_of_images[0].dtype
    if len(list_of_images) < n_rows * n_cols:
        white = np.zeros(list_of_images[0].shape, dtype=dtype)
        n_missing = n_rows * n_cols - len(list_of_images)
        list_of_images += [white,] * n_missing
    return np.vstack([np.hstack(list_of_images[i_row*n_cols:
                                               i_row*n_cols + n_cols])
                      for i_row in range(n_rows)])


def untile_images(image_string, n_rows, n_cols):
    big_im = np.asarray(image_string_to_PILImage(image_string))
    tiles = [np.split(im, n_cols, axis=1) for im in np.split(big_im, n_rows)]
    return np.array(tiles)

def instructions():
    return html.Div(children=[
    html.H5(children='How to use this stitching app'),
    dcc.Markdown("""
    - Choose the number of rows and columns of the mosaic,
    - Upload images.
    - Try automatic stitching by pressing
    the "Run stitching" button.
    - If automatic stitching did not work,
    try adjusting the overlap parameter.

    If shifts between different images are very diifferent,
    draw lines to match points of interest in pairs of
    images, then press "Estimate translation" to compute an
    estimate of the shifts, then press "Run stitching".
    """)
    ])

app = dash.Dash(__name__)
server = app.server
app.config.suppress_callback_exceptions = False

height, width = 200, 500
canvas_width = 800
canvas_height = round(height * canvas_width / width)
scale = canvas_width / width

list_columns = ['length', 'width', 'height']
columns = [{"name": i, "id": i} for i in list_columns]


app.layout = html.Div([
    html.Div([
        dcc.Tabs(
            id='stitching-tabs',
            value='canvas-tab',
            children=[
                dcc.Tab(
                    label='Image tiles',
                    value='canvas-tab',
                    children=[
                        dash_canvas.DashCanvas(
                            id='canvas-stitch',
                            label='my-label',
                            width=canvas_width,
                            height=canvas_height,
                            scale=scale,
                            lineWidth=2,
                            lineColor='red',
                            tool="line",
                            image_content=array_to_data_url(
                                np.zeros((width, width), dtype=np.uint8)),
                            goButtonTitle='Estimate translation',
                        ),
                        image_upload_zone('upload-stitch', multiple=True,
                            width=45),
                        html.Div(id='sh_x', hidden=True),
                    ]
                ),
                dcc.Tab(
                    label='Stitched Image',
                    value='result-tab',
                    children=[
                        html.Img(id='stitching-result',
                            src=array_to_data_url(
                                np.zeros((height, width), dtype=np.uint8)),
                            width=canvas_width)

                        ]
                    )
            ]
            )
    ], className="eight columns"),
    html.Div([
        html.Label('Number of rows'),
        dcc.Input(
            id='nrows-stitch',
            type='number',
            value=1,
            name='number of rows',
            ),
        html.Label('Number of columns'),
        dcc.Input(
            id='ncolumns-stitch',
            type='number',
            value=2,
            name='number of columns',
            ),
        html.Label('Fraction of overlap (in [0-1] range)'),
        dcc.Input(
            id='overlap-stitch',
            type='float',
            value=0.15,
            ),
        html.Label('Measured shifts between images'),
        dash_table.DataTable(
            id='table-stitch',
            columns=columns,
            editable=True,
            ),

        html.Div(id='estimate-stitch'),
        html.Br(),
        html.Button('Run stitching', id='button-stitch',
                                     style={'color':'red'}),
        html.Br(),
        instructions()
    ], className="three columns"),
    ])


def update_canvas_upload(list_image_string, list_filenames, nrows, ncols):
    if list_image_string is None:
        raise PreventUpdate
    if list_image_string is not None:
        print('update canvas upload')
        order = np.argsort(list_filenames)
        image_list = [np.asarray(image_string_to_PILImage(list_image_string[i])) for i in
                order]
        res = tile_images(image_list, nrows, ncols)
        np.save('res.npy', res)
        return array_to_data_url(res)
    else:
        return None


def perform_registration(n_cl, n_rows, n_cols, overlap, estimate, image_string):
    print(overlap, estimate)
    tiles = untile_images(image_string, n_rows, n_cols)
    if estimate is not None and len(estimate) > 0:
        overlap = []
        for line in estimate:
            print(line)
            overlap.append(1.1 * line['length'] / tiles.shape[3])
            print("overlap is", overlap, line['length'])

    canvas = register_tiles(tiles, n_rows, n_cols,
                            overlaps=overlap,
                            pad=100)
    return array_to_data_url(canvas)


@app.callback(Output('table-stitch', 'data'),
             [Input('canvas-stitch', 'json_data')])
def estimate_translation(string):
    props = parse_jsonstring_line(string)
    df = pd.DataFrame(props, columns=list_columns)
    return df.to_dict("records")


@app.callback(Output('sh_x', 'children'),
              [Input('upload-stitch', 'contents'),
               Input('upload-stitch', 'filename')],
              [State('nrows-stitch', 'value'),
               State('ncolumns-stitch', 'value')])
def upload_content(list_image_string, list_filenames, n_rows, n_cols):
    return update_canvas_upload(list_image_string, list_filenames,
                                n_rows, n_cols)



@app.callback(Output('stitching-tabs', 'value'),
              [Input('button-stitch', 'n_clicks')])
def change_focus(click):
    print('changing focus')
    if click:
        return 'result-tab'
    return 'canvas-tab'

@app.callback(Output('stitching-result', 'src'),
              [Input('button-stitch', 'n_clicks')],
              [State('nrows-stitch', 'value'),
               State('ncolumns-stitch', 'value'),
               State('overlap-stitch', 'value'),
               State('table-stitch', 'data'),
               State('sh_x', 'children')])
def modify_content(n_cl, n_rows, n_cols, overlap, table, image_string):
    return perform_registration(n_cl, n_rows, n_cols, overlap, table,
                                image_string)


@app.callback(Output('canvas-stitch', 'image_content'),
              [Input('sh_x', 'children')])
def update_canvas_image(im):
    print('update image content')
    return im


@app.callback(Output('canvas-stitch', 'height'),
              [Input('sh_x', 'children')],
              [State('canvas-stitch', 'width'),
               State('canvas-stitch', 'height')])
def update_canvas_upload_shape(image_string, w, h):
    if image_string is None:
        raise PreventUpdate
    if image_string is not None:
        im = image_string_to_PILImage(image_string)
        im_h, im_w = im.height, im.width
        return round(w / im_w * im_h)
    else:
        return canvas_height


@app.callback(Output('canvas-stitch', 'scale'),
              [Input('sh_x', 'children')])
def update_canvas_upload_scale(image_string):
    if image_string is None:
        raise PreventUpdate
    if image_string is not None:
        # very dirty hack, this should be made more robust using regexp
        im = image_string_to_PILImage(image_string)
        im_h, im_w = im.height, im.width
        return canvas_width / im_w
    else:
        return scale



if __name__ == "__main__":
    with launch_ipdb_on_exception():
        app.run_server(debug=True)
