
import pickle
import cv2
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation

from PIL import Image, ImageDraw
from face_recognition import face_landmarks


def find_landmarks(img):

    dict_to_list = lambda d: [x for l in d.values() for x in l]

    landmarks_found = face_landmarks(np.array(img))
    if len(landmarks_found) > 0:
        return dict_to_list(landmarks_found[0])
    else:
        raise Exception("Failed to find face landmarks for one of the images.")


def delauney(points, img, draw=False):
    """
    Finds Delauney's triangulation of the list of points
    in an img, and draw it if necessary.
    
    Args:
        points: A list of 2D points as tuples.
        img: The image of containing the points as a PIL or numpy.
        draw: Draw the triangulation on the img if True.
        
    """
    
    # Init subdiv and insert points
    _, h, w =  np.array(img).shape
    xs, ys = zip(*points)
    rect_x = min(0, min(xs))
    rect_y  = min(0, min(ys))
    rect_w = max(w, max(xs) - rect_x) + 1
    rect_h = max(h, max(ys) - rect_y) + 1
    
    rect = (rect_x, rect_y, rect_w, rect_h)
    subdiv = cv2.Subdiv2D(rect)
    subdiv.insert(points)

    triangles = []
    for t in subdiv.getTriangleList():
        # Get triangle point
        t = np.int32(t)
        p1 = (t[0], t[1])
        p2 = (t[2], t[3])
        p3 = (t[4], t[5])
        t = tuple(sorted([p1, p2, p3]))
        triangles.append(t)

    return sorted(triangles)


def warp_triangle(t1, t2, img1, img2, alpha=0.8):
    """
    Warps triangle1 in img1 to triangle2 in img2 by a factor of alpha.
    
    Args:
        t1: A list of 3 points (or tuples) of the triangle in img1.
        t2: A list of 3 points (or tuples) of the triangle in img2.
        img1: Tthe source image as a numpy array.
        img2: The destination image as a numpy array.
        alpha: Interpolation factor of the warp.
    """
    
    # Convert source and destination triangle to numpy
    t1 = np.float32(t1)
    t2 = np.float32(t2)

    # Get the bounding rectangles (patches) of the triangles
    x1, y1, w1, h1 = cv2.boundingRect(t1)
    x2, y2, w2, h2 = cv2.boundingRect(t2)
    
    # Sometimes, landmarks reside slightly outside the image... @XXX: hacky.
    x1, y1, x2, y2 = max(0, x1), max(0, y1), max(0, x2), max(0, y2)
    
    # Offset triangles' coordinates by the bounding rect's coordinates
    t1[:, 0] = t1[:, 0] - x1
    t1[:, 1] = t1[:, 1] - y1
    t2[:, 0] = t2[:, 0] - x2
    t2[:, 1] = t2[:, 1] - y2
    
    # Get the rectangles from the images
    patch1 = img1[y1:y1+h1, x1:x1+w1].copy()
    patch2 = img2[y2:y2+h2, x2:x2+w2].copy()

    # If one of the patches have length 0 in any dimension, skip this warp
    if 0 in patch1.shape or 0 in patch2.shape:
        return

    # Get the affine transformation between the triangles in the new coordinates
    affine1to2 = cv2.getAffineTransform(t1, t2)
    
    # Affine-warp patch1 to patch2
    #print("t1:", t1)
    #print(x1, y1, w1, h1)
    #print("patch1.shape:", patch1.shape)
    patch1_warped = cv2.warpAffine(patch1, affine1to2, (w2,h2),
                                   borderMode=cv2.BORDER_REFLECT_101)
    
    # Crop out points outside image on the max side. @XXX: hacky but ok.
    if patch1_warped.shape != patch2.shape:
        patch1_warped = patch1_warped[0:patch2.shape[0], 0:patch2.shape[1]]
        
    # Create a mask to get a t2-like triangle out of patch1_warped
    mask = cv2.fillConvexPoly(np.zeros_like(patch2), np.int32(t2), (1.0, 1.0, 1.0))
    
    # Now interpolate the warped t1 in patch1_warped to t2 by a factor of alpha
    mask = alpha * np.float32(mask)
    warped_patch = mask * patch1_warped + (1 - mask) * patch2
    
    # Paste the warped patch to img2 in place of patch2
    img2[y2:y2+h2, x2:x2+w2] = warped_patch
    
    return t1, t2, patch1, patch2, patch1_warped



def face_morph(img1, img2, landmarks1=None, landmarks2=None, alpha=0.95):
    """
    Morph face in img1 to face in img2 by a factor of alpha, given their landmarks.

    Args:
        img1: The source image as a PIL image or a numpy array.
        img2: The destination image as a PIL image or a numpy array.
        landmarks1: List of landmarks points from img1.
        landmarks2: List of landmarks points from img2.
        alpha: Factor of interpolation from face in img1 to face in img2.
    """

    # Convert PIL images to np arrays
    img_array1, img_array2 = np.array(img1), np.array(img2)

    # Find landmarks if none were given
    if landmarks1 is None: landmarks1 = find_landmarks(img1)
    if landmarks2 is None: landmarks2 = find_landmarks(img2)

    # Create a map that links the vertices of the two landmarks together
    points_map = dict(zip(landmarks1, landmarks2))

    # Warp each triangle in img1 to its corresponding one in img2
    for t1 in delauney(landmarks1, img1):
        t2 = tuple(map(lambda p: points_map[p], t1))
        warp_triangle(t1, t2, img_array1, img_array2, alpha=alpha)

    return img_array2


def face_morph_video(filename, img1, img2, landmarks1=None, landmarks2=None):

    # Convert PIL images to np arrays
    img_array1, img_array2 = np.array(img1), np.array(img2)

    # Find landmarks if none were given
    if landmarks1 is None: landmarks1 = find_landmarks(img1)
    if landmarks2 is None: landmarks2 = find_landmarks(img2)

    # Create a map that links the vertices of the two landmarks together
    points_map = dict(zip(landmarks1, landmarks2))

    # Find Delauney triangles of both landmarks
    triangles1 = delauney(landmarks1, img1)
    # triangles2 = delauney(landmarks2, img2)

    # Prepare figure and frames of morphed images
    fig = plt.figure()
    plt.axis('off')
    morphed_imgs = []

    # For each morphing factor `alpha`...
    step = 0.05
    for alpha in np.arange(0, 1.0, step):
        
        # Start morphed img from the original img2
        morphed_img = img_array2.copy()
        
        # Warp each triangle in img1 to its corresponding one in img2
        for t1 in triangles1:
            t2 = tuple(map(lambda p: points_map[p], t1))
            warp_triangle(t1, t2, img_array1, morphed_img, alpha=alpha)
        
        # save frame of morphed image to animate later
        morphed_imgs.append([plt.imshow(morphed_img, animated=True)])

    # Make animation and play
    ani = animation.ArtistAnimation(fig, morphed_imgs,
                                    interval=200, blit=True, repeat_delay=1000)
    ani.save(filename)


#############################################

def test(imgname1, imgname2):

    # File name of video
    filename = f"vid/{imgname1} --> {imgname2}.mp4"

    imgname1 = f"img/{imgname1}"
    imgname2 = f"img/{imgname2}"

    # Load images
    img1 = Image.open(imgname1)
    img2 = Image.open(imgname2)

    # Extract landmarks
    landmarks1 = find_landmarks(img1)
    landmarks2 = find_landmarks(img2)

    # Morph face
    face_morph_video(filename, img1, img2, landmarks1, landmarks2)


def main():
    test("00000-before.jpeg", "00000-after.jpeg")
    test("00000-after.jpeg", "00000-before.jpeg")

    test("00003-before.jpeg", "00003-after.jpeg")
    test("00003-after.jpeg", "00003-before.jpeg")

    test("00000-before.jpeg", "00003-before.jpeg")
    test("00003-before.jpeg", "00000-before.jpeg")

    test("00000-after.jpeg", "00003-after.jpeg")
    test("00003-after.jpeg", "00000-after.jpeg")

    test("00000-before.jpeg", "00003-after.jpeg")
    test("00003-after.jpeg", "00000-before.jpeg")

    test("00003-before.jpeg", "00000-after.jpeg")
    test("00000-after.jpeg", "00003-before.jpeg")


if __name__ == '__main__':
    main()

