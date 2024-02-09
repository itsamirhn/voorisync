import json
import os
from time import sleep

import click
import requests
from tqdm import tqdm

session = requests.Session()


def create_folders_and_sync(sub_dirs, parent_path, skip=None):
    if skip is None:
        skip = []
    for item in sub_dirs:
        item_type = item.get("type")
        item_title = item.get("title")
        item_key = item.get("key")
        if item_key in skip:
            click.secho(f"[SKIP] {item_key}: Skip List", fg="yellow")
            continue
        if item_type == "folder":
            folder_path = os.path.join(parent_path, item_title)
            os.makedirs(folder_path, exist_ok=True)
            yield from create_folders_and_sync(item.get("children", []), folder_path, skip)
        elif item_type == "file":
            file_path = os.path.join(parent_path, item_title)
            if not os.path.exists(file_path):
                click.secho(f"[QUEUE] {item_key}: {file_path}", fg="blue")
                yield item_key, file_path
            else:
                click.secho(f"[SKIP] {item_key}: Already Exist at {file_path}", fg="yellow")


def fetch_videos_json_data():
    response = session.get("https://dl-api.voorivex.academy/video")
    if response.status_code != 200:
        raise RuntimeError("Could not fetch videos")
    return json.loads(response.text)


def request_file_preparation(key):
    click.secho(f"[PREPARE] {key}", fg="blue")
    response = session.post(
        "https://dl-api.voorivex.academy/video/remove",
        json={"key": key},
    )
    if response.status_code != 201:
        raise RuntimeError("Could not remove old file")
    response = session.post(
        "https://dl-api.voorivex.academy/video/ganerate",
        json={"key": key},
    )
    if response.status_code != 201:
        raise RuntimeError("Could not generate new file")


def get_active_links():
    response = session.get("https://dl-api.voorivex.academy/video/getActiveLink")
    if response.status_code != 200:
        raise RuntimeError("Could not fetch active links")
    return json.loads(response.text)


def download_video(key, file_path):
    click.secho(f"[SYNC] {key}: {file_path}", fg="green")
    request_file_preparation(key)
    while True:
        active_links = get_active_links()
        for video in active_links.get("videos", []):
            if video.get("key") == key:
                click.secho(f"[DOWNLOAD] {key}", fg="green")
                download_and_save_file_with_rollback(video.get("url"), file_path)
                click.secho(f"[DONE] {key}", fg="green")
                return
        click.secho(f"[WAIT] {key}", fg="blue", blink=True)
        sleep(1)


def download_and_save_file(url, file_path):
    response = session.get(url, stream=True)

    total_size = int(response.headers.get("content-length", 0))
    block_size = 1024

    with tqdm(total=total_size, unit="B", unit_scale=True, desc=file_path) as progress_bar:
        with open(file_path, "wb") as file:
            for data in response.iter_content(block_size):
                progress_bar.update(len(data))
                file.write(data)

    if total_size != 0 and progress_bar.n != total_size:
        raise RuntimeError(f"Could not download: {url}")


def download_and_save_file_with_rollback(url, file_path):
    try:
        download_and_save_file(url, file_path)
    except KeyboardInterrupt:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise


@click.command(
    help="Sync Voorivex videos to your local machine",
)
@click.option(
    "--token",
    prompt=True,
    help="dl-token key in the cookies (go to https://voorivex.academy/download/",
)
@click.option(
    "--path",
    default="voorivex",
    type=click.Path(exists=True, file_okay=False, writable=True),
    help="Path to sync the videos",
)
@click.option("--skip", default=[], multiple=True, help="Skip the videos with the given keys")
def main(token, path, skip):

    session.headers.update({"Authorization": f"Bearer {token}"})
    try:
        videos_json_data = fetch_videos_json_data()
        for key, file_path in create_folders_and_sync(videos_json_data, path, skip):
            download_video(key, file_path)
        click.secho("[DONE] All videos are synced!", fg="green")
    except Exception as e:
        click.secho(f"[ERROR] {e}", fg="red")


if __name__ == "__main__":
    main()
