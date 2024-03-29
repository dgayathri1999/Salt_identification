#!/usr/bin/env python
# coding: utf-8

# In[1]:


import os
import random
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
plt.style.use("ggplot")
get_ipython().run_line_magic('matplotlib', 'inline')

from tqdm import tqdm_notebook, tnrange
from itertools import chain
from skimage.io import imread, imshow, concatenate_images
from skimage.transform import resize
from skimage.morphology import label
from sklearn.model_selection import train_test_split

import tensorflow as tf

from keras.models import Model, load_model
from keras.layers import Input, BatchNormalization, Activation, Dense, Dropout
from keras.layers.core import Lambda, RepeatVector, Reshape
from keras.layers.convolutional import Conv2D, Conv2DTranspose
from keras.layers.pooling import MaxPooling2D, GlobalMaxPool2D
from keras.layers.merge import concatenate, add
from keras.callbacks import EarlyStopping, ModelCheckpoint, ReduceLROnPlateau
from keras.optimizers import Adam
from keras.preprocessing.image import ImageDataGenerator, array_to_img, img_to_array, load_img


# In[2]:


# Set some parameters
im_width = 128
im_height = 128
border = 5


# In[13]:


ids = next(os.walk("/home/gayathri/Desktop/driver behavoir/night_to_day/tgs-salt-identification-challenge/train/images"))[2] # list of names all images in the given path
print("No. of images = ", len(ids))


# In[14]:


X = np.zeros((len(ids), im_height, im_width, 1), dtype=np.float32)
y = np.zeros((len(ids), im_height, im_width, 1), dtype=np.float32)


# #### Load the images and masks into arrays

# In[15]:


# tqdm is used to display the progress bar
for n, id_ in tqdm_notebook(enumerate(ids), total=len(ids)):
    # Load images
    img = load_img("/home/gayathri/Desktop/driver behavoir/night_to_day/tgs-salt-identification-challenge/train/images/"+id_, grayscale=True)
    x_img = img_to_array(img)
    x_img = resize(x_img, (128, 128, 1), mode = 'constant', preserve_range = True)
    # Load masks
    mask = img_to_array(load_img("/home/gayathri/Desktop/driver behavoir/night_to_day/tgs-salt-identification-challenge/train/masks/"+id_, grayscale=True))
    mask = resize(mask, (128, 128, 1), mode = 'constant', preserve_range = True)
    # Save images
    X[n] = x_img/255.0
    y[n] = mask/255.0


# In[16]:


# Split train and valid
X_train, X_valid, y_train, y_valid = train_test_split(X, y, test_size=0.1, random_state=42)


# #### Below code can be used to visualize the images and corresponding masks

# In[17]:


# Visualize any randome image along with the mask
ix = random.randint(0, len(X_train))
has_mask = y_train[ix].max() > 0 # salt indicator

fig, (ax1, ax2) = plt.subplots(1, 2, figsize = (20, 15))

ax1.imshow(X_train[ix, ..., 0], cmap = 'seismic', interpolation = 'bilinear')
if has_mask: # if salt
    # draw a boundary(contour) in the original image separating salt and non-salt areas
    ax1.contour(y_train[ix].squeeze(), colors = 'k', linewidths = 5, levels = [0.5])
ax1.set_title('Seismic')

ax2.imshow(y_train[ix].squeeze(), cmap = 'gray', interpolation = 'bilinear')
ax2.set_title('Salt')


# In[18]:


def conv2d_block(input_tensor, n_filters, kernel_size = 3, batchnorm = True):
    """Function to add 2 convolutional layers with the parameters passed to it"""
    # first layer
    x = Conv2D(filters = n_filters, kernel_size = (kernel_size, kernel_size),              kernel_initializer = 'he_normal', padding = 'same')(input_tensor)
    if batchnorm:
        x = BatchNormalization()(x)
    x = Activation('relu')(x)
    
    # second layer
    x = Conv2D(filters = n_filters, kernel_size = (kernel_size, kernel_size),              kernel_initializer = 'he_normal', padding = 'same')(input_tensor)
    if batchnorm:
        x = BatchNormalization()(x)
    x = Activation('relu')(x)
    
    return x


# In[19]:


def get_unet(input_img, n_filters = 16, dropout = 0.1, batchnorm = True):
    """Function to define the UNET Model"""
    # Contracting Path
    c1 = conv2d_block(input_img, n_filters * 1, kernel_size = 3, batchnorm = batchnorm)
    p1 = MaxPooling2D((2, 2))(c1)
    p1 = Dropout(dropout)(p1)
    
    c2 = conv2d_block(p1, n_filters * 2, kernel_size = 3, batchnorm = batchnorm)
    p2 = MaxPooling2D((2, 2))(c2)
    p2 = Dropout(dropout)(p2)
    
    c3 = conv2d_block(p2, n_filters * 4, kernel_size = 3, batchnorm = batchnorm)
    p3 = MaxPooling2D((2, 2))(c3)
    p3 = Dropout(dropout)(p3)
    
    c4 = conv2d_block(p3, n_filters * 8, kernel_size = 3, batchnorm = batchnorm)
    p4 = MaxPooling2D((2, 2))(c4)
    p4 = Dropout(dropout)(p4)
    
    c5 = conv2d_block(p4, n_filters = n_filters * 16, kernel_size = 3, batchnorm = batchnorm)
    
    # Expansive Path
    u6 = Conv2DTranspose(n_filters * 8, (3, 3), strides = (2, 2), padding = 'same')(c5)
    u6 = concatenate([u6, c4])
    u6 = Dropout(dropout)(u6)
    c6 = conv2d_block(u6, n_filters * 8, kernel_size = 3, batchnorm = batchnorm)
    
    u7 = Conv2DTranspose(n_filters * 4, (3, 3), strides = (2, 2), padding = 'same')(c6)
    u7 = concatenate([u7, c3])
    u7 = Dropout(dropout)(u7)
    c7 = conv2d_block(u7, n_filters * 4, kernel_size = 3, batchnorm = batchnorm)
    
    u8 = Conv2DTranspose(n_filters * 2, (3, 3), strides = (2, 2), padding = 'same')(c7)
    u8 = concatenate([u8, c2])
    u8 = Dropout(dropout)(u8)
    c8 = conv2d_block(u8, n_filters * 2, kernel_size = 3, batchnorm = batchnorm)
    
    u9 = Conv2DTranspose(n_filters * 1, (3, 3), strides = (2, 2), padding = 'same')(c8)
    u9 = concatenate([u9, c1])
    u9 = Dropout(dropout)(u9)
    c9 = conv2d_block(u9, n_filters * 1, kernel_size = 3, batchnorm = batchnorm)
    
    outputs = Conv2D(1, (1, 1), activation='sigmoid')(c9)
    model = Model(inputs=[input_img], outputs=[outputs])
    return model


# In[20]:


input_img = Input((im_height, im_width, 1), name='img')
model = get_unet(input_img, n_filters=16, dropout=0.05, batchnorm=True)
model.compile(optimizer=Adam(), loss="binary_crossentropy", metrics=["accuracy"])


# In[21]:


model.summary()


# In[22]:


callbacks = [
    EarlyStopping(patience=10, verbose=1),
    ReduceLROnPlateau(factor=0.1, patience=5, min_lr=0.00001, verbose=1),
    ModelCheckpoint('/home/gayathri/Desktop/driver behavoir/night_to_day/tgs-salt-identification-challenge/model-tgs-salt.h5', verbose=1, save_best_only=True, save_weights_only=True)
]


# In[24]:


results = model.fit(X_train, y_train, batch_size=32, epochs=20, callbacks=callbacks,                    validation_data=(X_valid, y_valid))


# In[25]:


plt.figure(figsize=(8, 8))
plt.title("Learning curve")
plt.plot(results.history["loss"], label="loss")
plt.plot(results.history["val_loss"], label="val_loss")
plt.plot( np.argmin(results.history["val_loss"]), np.min(results.history["val_loss"]), marker="x", color="r", label="best model")
plt.xlabel("Epochs")
plt.ylabel("log_loss")
plt.legend();


# ### Inference

# In[28]:


# load the best model
model.load_weights('/home/gayathri/Desktop/driver behavoir/night_to_day/tgs-salt-identification-challenge/model-tgs-salt.h5')


# In[29]:


# Evaluate on validation set (this must be equals to the best log_loss)
model.evaluate(X_valid, y_valid, verbose=1)


# In[30]:


# Predict on train, val and test
preds_train = model.predict(X_train, verbose=1)
preds_val = model.predict(X_valid, verbose=1)


# In[31]:


# Threshold predictions
preds_train_t = (preds_train > 0.5).astype(np.uint8)
preds_val_t = (preds_val > 0.5).astype(np.uint8)


# In[32]:


def plot_sample(X, y, preds, binary_preds, ix=None):
    """Function to plot the results"""
    if ix is None:
        ix = random.randint(0, len(X))

    has_mask = y[ix].max() > 0

    fig, ax = plt.subplots(1, 4, figsize=(20, 10))
    ax[0].imshow(X[ix, ..., 0], cmap='seismic')
    if has_mask:
        ax[0].contour(y[ix].squeeze(), colors='k', levels=[0.5])
    ax[0].set_title('Seismic')

    ax[1].imshow(y[ix].squeeze())
    ax[1].set_title('Salt')

    ax[2].imshow(preds[ix].squeeze(), vmin=0, vmax=1)
    if has_mask:
        ax[2].contour(y[ix].squeeze(), colors='k', levels=[0.5])
    ax[2].set_title('Salt Predicted')
    
    ax[3].imshow(binary_preds[ix].squeeze(), vmin=0, vmax=1)
    if has_mask:
        ax[3].contour(y[ix].squeeze(), colors='k', levels=[0.5])
    ax[3].set_title('Salt Predicted binary');


# ### Predictions on training set

# In[36]:


# Check if training data looks all right
plot_sample(X_train, y_train, preds_train, preds_train_t, ix=14)


# In[37]:


plot_sample(X_train, y_train, preds_train, preds_train_t)


# In[38]:


plot_sample(X_train, y_train, preds_train, preds_train_t)


# In[39]:


plot_sample(X_train, y_train, preds_train, preds_train_t)


# In[40]:


plot_sample(X_train, y_train, preds_train, preds_train_t)


# In[41]:


plot_sample(X_train, y_train, preds_train, preds_train_t)


# In[42]:


plot_sample(X_train, y_train, preds_train, preds_train_t)


# In[43]:


plot_sample(X_train, y_train, preds_train, preds_train_t)


# In[44]:


plot_sample(X_train, y_train, preds_train, preds_train_t)


# In[45]:


plot_sample(X_train, y_train, preds_train, preds_train_t)


# In[46]:


plot_sample(X_train, y_train, preds_train, preds_train_t)


# In[47]:


plot_sample(X_train, y_train, preds_train, preds_train_t)


# In[ ]:





# In[ ]:





# ### Predictions on test set

# In[48]:


# Check if valid data looks all right
plot_sample(X_valid, y_valid, preds_val, preds_val_t, ix=19)


# In[49]:


plot_sample(X_valid, y_valid, preds_val, preds_val_t)


# In[50]:


plot_sample(X_valid, y_valid, preds_val, preds_val_t)


# In[51]:


plot_sample(X_valid, y_valid, preds_val, preds_val_t)


# In[52]:


plot_sample(X_valid, y_valid, preds_val, preds_val_t)


# In[53]:


plot_sample(X_valid, y_valid, preds_val, preds_val_t)


# In[54]:


plot_sample(X_valid, y_valid, preds_val, preds_val_t)


# In[55]:


plot_sample(X_valid, y_valid, preds_val, preds_val_t)


# In[56]:


plot_sample(X_valid, y_valid, preds_val, preds_val_t)


# In[57]:


plot_sample(X_valid, y_valid, preds_val, preds_val_t)


# In[58]:


plot_sample(X_valid, y_valid, preds_val, preds_val_t)


# In[59]:


plot_sample(X_valid, y_valid, preds_val, preds_val_t)


# In[60]:


plot_sample(X_valid, y_valid, preds_val, preds_val_t)


# In[61]:


plot_sample(X_valid, y_valid, preds_val, preds_val_t)


# In[62]:


plot_sample(X_valid, y_valid, preds_val, preds_val_t)


# In[63]:


plot_sample(X_valid, y_valid, preds_val, preds_val_t)


# In[ ]:




