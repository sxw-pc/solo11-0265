"""Load lifetimes for simulated profiler recordings, with half-open ranges."""


def locate(images, at, address):
    loaded = [image for image in images if image['begin'] <= at < image['end']
              and image['base'] <= address < image['base'] + image['size']]
    if len(loaded) != 1:
        return None
    selected = loaded[0]
    return selected['build'], address - selected['base']
