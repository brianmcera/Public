import tensorflow as tf
import tensorflow_probability as tfp
import numpy as np
from sklearn import preprocessing, decomposition
import matplotlib.pyplot as plt
import datetime
import time
import gym
import pdb
import random
from tensorflow.keras import Model, layers
from tensorflow.keras.layers import Dense, Flatten, Conv2D, Dropout, MaxPool2D, BatchNormalization

class policyMu(Model):
    """
    This class defines the control policy NN model for LunarLander environment.
    Given an input of a batch of state-vectors, it will return a batch of optimized controller inputs.
    It features dense fully-connected layers with batch normalization and dropout for regularization and more stable learning.
    """
    def __init__(self, ob_dim, ac_dim):
        super(policyMu, self).__init__()
        self.d1 = Dense(5, input_shape=ob_dim, activation='relu', kernel_regularizer=tf.keras.regularizers.l2(1e-4))
        self.d2 = Dense(20, activation='relu', kernel_regularizer=tf.keras.regularizers.l2(1e-3))
        self.d3 = Dense(20, activation='relu', kernel_regularizer=tf.keras.regularizers.l2(1e-3))
        self.d4 = Dense(10, activation='relu', kernel_regularizer=tf.keras.regularizers.l2(1e-3))
        self.d5 = Dense(10, activation='relu', kernel_regularizer=tf.keras.regularizers.l2(1e-3))
        self.d6 = Dense(ac_dim, activation='tanh')
        self.dropout = Dropout(rate=0.5)
        self.batchnormalization = BatchNormalization()
        self.batchnormalization2 = BatchNormalization()

    def call(self, x):
        x = self.d1(x)
        x = self.d2(x)
        x = self.batchnormalization(x)
        x = self.d3(x)
        x = self.dropout(x)
        x = self.d4(x)
        x = self.d5(x)
        return self.d6(x)

class baselineNN(Model):
    """
    This class defines the baseline critic model for the LunarLander env.
    Given an input of a batch of state-vectors, it will return a batch of approximate value function estimates.
    It features dense fully-connected layers with batch normalization and ropout for regularization and stable learning.
    """
    def __init__(self, ob_dim):
        super(baselineNN, self).__init__()
        self.d1 = Dense(5, input_shape=ob_dim, activation='relu', kernel_regularizer=tf.keras.regularizers.l2(1e-4))
        self.d2 = Dense(10, activation='relu', kernel_regularizer=tf.keras.regularizers.l2(1e-4))
        self.d3 = Dense(10, activation='relu', kernel_regularizer=tf.keras.regularizers.l2(1e-4))
        self.d4 = Dense(5, activation='relu', kernel_regularizer=tf.keras.regularizers.l2(1e-4))
        self.d5 = Dense(5, activation='relu', kernel_regularizer=tf.keras.regularizers.l2(1e-4))
        self.dropout = Dropout(rate=0.5)
        self.batchnormalization = BatchNormalization()
        self.batchnormalization2 = BatchNormalization()
        self.d6 = Dense(1) 

    def call(self, x):
        x = self.d1(x)
        x = self.d2(x)
        x = self.batchnormalization(x)
        x = self.d3(x)
        x = self.dropout(x)
        x = self.d4(x)
        x = self.d5(x)
        return self.d6(x)
    
def sample_trajectories(num_traj, num_steps, env, controller, scaler, transformer, show_visual=False, first_run=False, normalize_inputs=True):
    """
    This function will sample the OpenAI Gym environment for sample trajectories used for reinforcement learning.
    """
    return_vec = np.array([])
    for traj_num in range(num_traj):
        ob = env.reset()
        obs, next_obs, acs, rewards, returns, reward_to_go = [], [], [], [], [], []
        steps = 0
        ret = 0
        while True:
            if(show_visual or traj_num==0):
                env.render()
            obs.append(ob)
            if(first_run):
                ac = env.action_space.sample() 
            else:
                inputs = np.expand_dims(ob.astype(np.float32),0) 
                inputs = inputs + 1e-2*np.random.standard_normal(inputs.shape[1:])
                # normalize inputs
                if(normalize_inputs):
                    inputs = scaler.transform(inputs)
                    inputs = transformer.transform(inputs)
                ac = controller(inputs)[0]
            ac = np.array(ac)
            if(np.any(np.isnan(ac))):
                print('nan error')
                pdb.set_trace()
            if(not isinstance(env.action_space, gym.spaces.Discrete)):
                ac = np.minimum(ac,env.action_space.high)
                ac = np.maximum(ac,env.action_space.low)
            acs.append(ac)
            ob, reward, done, info = env.step(ac)

            reward -= 1e2*ob[0]**2 # custom: penalize deviation from x=0
            next_obs.append(ob)
            rewards.append(reward)
            ret += reward
            returns.append(ret)
            steps += 1

            if done or steps>num_steps:
                rewards[-1] -= 500
                returns[-1] -= 500
                print("Episode {} finished after {} timesteps".format(traj_num, steps))
                break

        # backwards pass to calculate reward-to-go
        reward_to_go = np.full(len(rewards),np.nan)
        discount = 0.80
        reward_to_go[-1] = rewards[-1]
        for i in range(2, reward_to_go.shape[0]+1):
            reward_to_go[-(i)] = rewards[-(i)] + discount*reward_to_go[-(i-1)] 
        
        print('run return: {}'.format(returns[-1]))
        if(traj_num==0):
            trajectories = {"observations" : np.array(obs),
                "next_observations": np.array(next_obs),
                "rewards" : np.array(rewards),
                "actions" : np.array(acs),
                "returns" : np.array(returns),
                "reward_to_go" : np.array(reward_to_go)}
        else:
            traj = {"observations" : np.array(obs),
                "next_observations": np.array(next_obs),
                "rewards" : np.array(rewards),
                "actions" : np.array(acs),
                "returns" : np.array(returns),
                "reward_to_go" : np.array(reward_to_go)}
            for k in traj:
                trajectories[k] = np.append(trajectories[k],traj[k],axis=0)
        return_vec = np.append(return_vec, returns[-1])
    return trajectories, return_vec

def compute_normalized_data(data):
    """
    This function calculates simple data statistics for later use.
    """
    obs_mean = tf.math.reduce_mean(tf.cast(data['observations'],tf.float32),axis=0)
    obs_std = tf.math.reduce_std(tf.cast(data['observations'],tf.float32),axis=0) + 1e-6*tf.ones(data['observations'].shape[1:])
    return (obs_mean, obs_std)#, acs_mean, acs_std)

def main():
    random.seed(0)
    tf.random.set_seed(0)
    #enable dynamic GPU memory allocation
    physical_devices = tf.config.experimental.list_physical_devices('GPU')
    assert len(physical_devices) > 0
    tf.config.experimental.set_memory_growth(physical_devices[0], True)
    tf.keras.backend.set_floatx('float64')

    
    # set up tensorboard logging
    current_time = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    train_log_dir = 'logs/gradient_tape/' + current_time + '/train'
    test_log_dir = 'logs/gradient_tape/' + current_time + '/test'
    train_summary_writer = tf.summary.create_file_writer(train_log_dir)
    test_summary_writer = tf.summary.create_file_writer(test_log_dir)

    # initialize environment and deep model
    env = gym.make('LunarLanderContinuous-v2') # define chosen environment here
    discrete = isinstance(env.action_space, gym.spaces.Discrete)
    ob_dim = env.observation_space.shape
    ac_dim = env.action_space.n if discrete else env.action_space.shape[0]

    optimizer1 = tf.keras.optimizers.Adam(learning_rate=1e-3) # baseline optimizer
    optimizer2 = tf.keras.optimizers.Adam(learning_rate=1e-4) # controller optimizer - smaller stepsize

    loss_object = tf.keras.losses.MeanSquaredError() 
    baseline_loss_object = tf.keras.losses.MeanSquaredError()

    train_MSE_metric = tf.keras.metrics.MeanSquaredError()
    train_weightedMSE_metric = tf.keras.metrics.MeanSquaredError()
    val_MSE_metric = tf.keras.metrics.MeanSquaredError()
    val_weightedMSE_metric = tf.keras.metrics.MeanSquaredError()

    controller = policyMu(ob_dim, ac_dim)
    controller.compile(optimizer = optimizer2,
                    loss = loss_object,
                    metrics = [])

    baseline = baselineNN(ob_dim)
    baseline.compile(optimizer = optimizer1,
                    loss = baseline_loss_object,
                    metrics = [])

    # make graph read-only to prevent accidentally adding nodes per iteration
    graph = tf.compat.v1.get_default_graph()
    graph.finalize()
    
    # TRAINING LOOP #################################################################
    #################################################################################
    training_epochs = 50
    first_run = True
    norm_constants = ()
    scaler = None
    transformer = None
    avg_return_vec = np.array([])
    std_return_vec = np.array([])
    max_return_vec = np.array([])
    plt.show()

    normalize_input = True # flag for toggling input normalization/kernel transformation
    for training_epoch in range(training_epochs):
        # generate training data 
        num_steps = 1000
        if(first_run):
            num_traj = 100
        else:
            num_traj = 20
        data, return_vec = sample_trajectories(num_traj, num_steps, env, controller, 
                                                scaler, transformer, show_visual=True, 
                                                first_run=first_run, normalize_inputs=normalize_input)

        # output current training rewards
        print('The maximum return is {}'.format(tf.math.reduce_max(data['returns'])))
        print('The average return is {}'.format(tf.math.reduce_mean(data['returns'])))
        print('The standard deviation of return is {}'.format(tf.math.reduce_std(data['returns'])))
        avg_return_vec = np.append(avg_return_vec, np.mean(return_vec))
        std_return_vec = np.append(std_return_vec, np.std(return_vec))
        max_return_vec = np.append(max_return_vec, np.max(return_vec))
        print(avg_return_vec)
        if(False):
            plt.plot(avg_return_vec)
            plt.plot(avg_return_vec + std_return_vec, ':')
            plt.plot(avg_return_vec - std_return_vec, ':')
            plt.draw()
            plt.pause(1e-3)

        # calculate normalized statistics, preprocess to improve training
        if(first_run):
            norm_constants = compute_normalized_data(data)
            scaler = preprocessing.StandardScaler()
            scaler.fit(data['observations'])
            X_normalized = scaler.transform(data['observations'])
            transformer = decomposition.KernelPCA(n_components=data['observations'].shape[-1], kernel='linear')
            X_transformed = transformer.fit_transform(X_normalized)
            fig, axes = plt.subplots(8,2)
            first_obs = data['observations']
            for i in range(first_obs.shape[1]):
                axes[i,0].hist(first_obs[:,i])
                axes[i,1].hist(X_transformed[:,i])
            fig.suptitle('Initial Data Preprocessing')
            print(np.std(first_obs, axis=0))
            print(np.std(X_transformed, axis=0))
            plt.show()
            input('Paused~')
        
        # collect data
        obs_data = data['observations']
        if(normalize_input):
            obs_data = scaler.transform(obs_data)
            obs_data = transformer.transform(obs_data)
        acs_data = data['actions']
        reward_to_go = data['reward_to_go']
        num_samples = data['observations'].shape[0]

        # make sure no NaN data errors
        if(np.any(np.isnan(reward_to_go))):
            print('nan error')
            program_pause = raw_input("reward to go NaNs")
        if(np.any(np.isnan(obs_data))):
            print('nan error')
            program_pause = raw_input("observation NaNs")
        if(np.any(np.isnan(acs_data))):
            print('nan error')
            program_pause = raw_input("action NaNs")


        # baseline neural network training
        print('Training baseline network...')
        batch_size = 512
        split_size = 8
        baseline_dataset = tf.data.Dataset.from_tensor_slices((obs_data[:-num_samples//split_size], reward_to_go[:-num_samples//split_size])).shuffle(1024).batch(batch_size)
        baseline_validation = tf.data.Dataset.from_tensor_slices((obs_data[-num_samples//split_size:], reward_to_go[-num_samples//split_size:])).shuffle(1024).batch(batch_size)

        baseline.fit(baseline_dataset, epochs=10, validation_data=baseline_validation)

        # manually defined gradient descent - useful for debugging
        for epoch in []:#range(10):
            print('Start of epoch %d' % (epoch,))

            # iterate over batches of dataset
            for step, (x_batch_train, y_batch_train) in enumerate(baseline_dataset):
                with tf.GradientTape() as tape:
                    model_output = baseline(x_batch_train)
                    loss_value = baseline_loss_object(y_batch_train,model_output, sample_weight=1/y_batch_train.shape[0])
                grads = tape.gradient(loss_value, baseline.trainable_weights)
                optimizer1.apply_gradients(zip(grads, baseline.trainable_weights))

                # update training metric
                train_MSE_metric(y_batch_train, model_output, sample_weight=1/y_batch_train.shape[0])

                # log every 20 batches
                if step % 20 == 0:
                    print('Training loss (for one batch) at step %s: %s' % (step, float(loss_value)))
                    print('Seen so far: %s samples' % ((step+1) * batch_size))

            # display training metrics at the end of each epoch
            train_MSE = train_MSE_metric.result()
            print('Baseline - Training MSE over epoch: %s' % (float(train_MSE),))
            # reset training metrics at the end of each epoch
            train_MSE_metric.reset_states()

            # run a validation loop at the end of each epoch
            for x_batch_val, y_batch_val in baseline_validation:
                val_output = baseline(x_batch_val)
                #update val metrics
                val_MSE_metric(y_batch_val,val_output, sample_weight=1/y_batch_val.shape[0])
            val_MSE = val_MSE_metric.result()
            val_MSE_metric.reset_states()
            print('Baseline - Validation MSE: %s' % (float(val_MSE),))

                    
        print('')
        # control policy training #######################################################
        #################################################################################
        print('Training policy network...')
        batch_size = 512
        split_size = 8
        if(1 and not first_run): # baseline network normalization
            reward_to_go -= baseline(obs_data)[:,0]
            reward_to_go = np.divide(reward_to_go, np.std(reward_to_go)+1e-8)
            reward_to_go -= np.mean(reward_to_go)
        elif(0):
            reward_to_go -= np.mean(reward_to_go)
            reward_to_go = np.divide(reward_to_go,np.std(reward_to_go)+1e-8)

        train_dataset = tf.data.Dataset.from_tensor_slices(
                (obs_data[:-num_samples//split_size], 
                    acs_data[:-num_samples//split_size], 
                    reward_to_go[:-num_samples//split_size])
                ).shuffle(10000).batch(batch_size)
        validation_dataset = tf.data.Dataset.from_tensor_slices(
                (obs_data[-num_samples//split_size:], 
                    acs_data[-num_samples//split_size:], 
                    reward_to_go[-num_samples//split_size:])
                ).shuffle(10000).batch(batch_size)

        controller.fit(train_dataset, epochs=1, validation_data=validation_dataset)

        # manually defined- gradient descent, useful for debugging 
        for epoch in []:#range(10):
            print('Start of epoch %d' % (epoch,))

            # iterate over batches of dataset
            for step, (x_batch_train, y_batch_train, reward_batch_train) in enumerate(train_dataset):
                with tf.GradientTape() as tape:
                    model_output = controller(x_batch_train)
                    loss_value = loss_object(y_batch_train, model_output, sample_weight = reward_batch_train/y_batch_train.shape[0])
                grads = tape.gradient(loss_value, controller.trainable_weights)
                optimizer2.apply_gradients(zip(grads, controller.trainable_weights))

                # update training metrics
                train_MSE_metric(y_batch_train, model_output, sample_weight=1/y_batch_train.shape[0])
                train_weightedMSE_metric(y_batch_train, model_output,
                        sample_weight=reward_batch_train/y_batch_train.shape[0])

                # log every 20 batches
                if step % 20 == 0:
                    print('Training loss (for one batch) at step %s: %s' % (step, float(loss_value)))
                    print('Seen so far: %s samples' % ((step+1) * batch_size))

            # display training metrics at the end of each epoch
            train_MSE = train_MSE_metric.result()
            weighted_MSE = train_weightedMSE_metric.result()

            print('Controller - Training MSE over epoch: %s' % (float(train_MSE),))
            print('Controller - Weighted training MSE over epoch: %s' % (float(weighted_MSE),))
            # reset training metrics at the end of each epoch
            train_MSE_metric.reset_states()
            train_weightedMSE_metric.reset_states()

            # run a validation loop at the end of each epoch
            for x_batch_val, y_batch_val, reward_batch_val in validation_dataset:
                val_output = controller(x_batch_val)
                #update val metrics
                val_weightedMSE_metric(y_batch_val, val_output,
                        sample_weight=reward_batch_val/y_batch_val.shape[0])
                val_MSE_metric(y_batch_val, val_output, sample_weight=1/y_batch_val.shape[0])
            val_MSE = val_MSE_metric.result()
            val_weightedMSE = val_weightedMSE_metric.result()
            val_MSE_metric.reset_states()
            val_weightedMSE_metric.reset_states()
            print('Controller - Validation MSE: %s' % (float(val_MSE),))
            print('Controller - Weighted validation MSE: %s' % (float(val_weightedMSE),))

        del obs_data, acs_data, reward_to_go, data
        first_run = False # toggle off after first run

    #controller.save('test_policy.h5')

if __name__ == "__main__":
    main()
        

