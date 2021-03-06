import numpy as np
import os
import random
import torch
from data.datamgr import SetDataManager
from options import parse_args, get_resume_file
from methods.LFTNet import LFTNet

# for loading pre-trained file
def loadWarmUpState(filename):
  print('  load pre-trained model file: {}'.format(filename))
  warmup_resume_file = get_resume_file(filename)
  tmp = torch.load(warmup_resume_file)
  if tmp is not None:
    state = tmp['state']
    state_keys = list(state.keys())
    for i, key in enumerate(state_keys):
      if "feature." in key:# and '.7.' not in key:
        newkey = key.replace("feature.","")
        state[newkey] = state.pop(key)
      else:
        state.pop(key)
  else:
    raise ValueError('No warm_up file')
  return state

# training iterations
def train(base_datamgr, base_set, val_loader, model, start_epoch, stop_epoch, params):

  # for validation
  max_acc = 0
  total_it = 0

  # training
  for epoch in range(start_epoch,stop_epoch):

    # randomly split seen domains to pseudo-seen and pseudo-unseen domains
    random_set = random.sample(base_set, k=2)
    ps_set = random_set[0]
    pu_set = random_set[1:]
    ps_loader = base_datamgr.get_data_loader(os.path.join(params.data_dir, ps_set, 'base.json'), aug=params.train_aug)
    pu_loader = base_datamgr.get_data_loader([os.path.join(params.data_dir, dataset, 'base.json') for dataset in pu_set], aug=params.train_aug)

    # train loop
    model.train()
    total_it = model.trainall_loop(epoch, ps_loader, pu_loader, total_it)

    # validate
    model.eval()
    with torch.no_grad():
      acc = model.test_loop(val_loader)

    # save
    if acc > max_acc:
      print("best model! save...")
      max_acc = acc
      outfile = os.path.join(params.checkpoint_dir, 'best_model.tar')
      model.save(outfile, epoch)
    else:
      print('GG!! best accuracy {:f}'.format(max_acc))
    if ((epoch + 1) % params.save_freq==0) or (epoch == stop_epoch - 1):
      outfile = os.path.join(params.checkpoint_dir, '{:d}.tar'.format(epoch + 1))
      model.save(outfile, epoch)

  return


# --- main function ---
if __name__=='__main__':

  # set numpy random seed
  np.random.seed(10)

  # parse argument
  params = parse_args('train')
  print('--- LFTNet training: {} ---'.format(params.name))
  print(params)

  # output and tensorboard dir
  params.tf_dir = '%s/log/%s'%(params.save_dir, params.name)
  params.checkpoint_dir = '%s/checkpoints/%s'%(params.save_dir, params.name)
  if not os.path.isdir(params.checkpoint_dir):
    os.makedirs(params.checkpoint_dir)

  # dataloader
  print('--- prepare dataloader ---')
  print('  train with multiple seen domains (unseen domain: {})'.format(params.testset))
  datasets = ['miniImagenet', 'cars', 'places', 'CUB', 'iNatPlantae']
  datasets.remove(params.testset)
  val_file = os.path.join(params.data_dir, 'miniImagenet', 'val.json')

  # model
  print('--- build LFTNet model ---')
  if 'Conv' in params.model:
    image_size = 84
  else:
    image_size = 224

  n_query = max(1, int(16* params.test_n_way/params.train_n_way))
  train_few_shot_params   = dict(n_way = params.train_n_way, n_support = params.n_shot)
  base_datamgr            = SetDataManager(image_size, n_query = n_query,  **train_few_shot_params)
  test_few_shot_params    = dict(n_way = params.test_n_way, n_support = params.n_shot)
  val_datamgr             = SetDataManager(image_size, n_query = n_query, **test_few_shot_params)
  val_loader              = val_datamgr.get_data_loader( val_file, aug = False)

  model = LFTNet(params, tf_path=params.tf_dir)
  model.cuda()

  # resume training
  start_epoch = params.start_epoch
  stop_epoch = params.stop_epoch
  if params.resume != '':
    resume_file = get_resume_file('%s/checkpoints/%s'%(params.save_dir, params.resume), params.resume_epoch)
    if resume_file is not None:
      start_epoch = model.resume(resume_file)
      print('  resume the training with at {} epoch (model file {})'.format(start_epoch, params.resume))
    else:
      raise ValueError('No resume file')
  # pre-train
  elif params.warmup != 'gg3b0':
    model.model.feature.load_state_dict(loadWarmUpState('%s/checkpoints/%s'%(params.save_dir, params.warmup)), strict=False)

  # training
  print('--- start the training ---')
  train(base_datamgr, datasets, val_loader, model, start_epoch, stop_epoch, params)
