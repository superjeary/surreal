from .base import Env, ActionType, ObsType
import numpy as np
import surreal.utils as U
import collections
from collections import deque
from operator import mul
import functools
import pygame
import sys
import gym
import dm_control
from dm_control.suite.wrappers import pixels
from dm_control.rl.environment import StepType

class SpecFormat(U.StringEnum):
    SURREAL_CLASSIC = ()
    DM_CONTROL = ()


class Wrapper(Env):
    # Clear metadata so by default we don't override any keys.
    metadata = {}
    # Make sure self.env is always defined, even if things break early.
    env = None

    def __init__(self, env):
        self.env = env
        # Merge with the base metadata
        metadata = self.metadata
        self.metadata = self.env.metadata.copy()
        self.metadata.update(metadata)
        self._ensure_no_double_wrap()
        # self.obs_spec = env.obs_spec
        # self.action_spec = env.action_spec

    @classmethod
    def class_name(cls):
        return cls.__name__

    def _ensure_no_double_wrap(self):
        env = self.env
        while True:
            if isinstance(env, Wrapper):
                if env.class_name() == self.class_name():
                    raise RuntimeError(
                        "Attempted to double wrap with Wrapper: {}"
                            .format(self.__class__.__name__)
                    )
                env = env.env
            else:
                break

    def _step(self, action):
        return self.env.step(action)

    def _reset(self):
        return self.env.reset()

    def _render(self, *args, **kwargs):
        return self.env.render(*args, **kwargs)

    def _close(self):
        return self.env.close()

    def __str__(self):
        return '<{}{}>'.format(type(self).__name__, self.env)

    def __repr__(self):
        return str(self)

    def action_spec(self):
        return self.env.action_spec()

    def observation_spec(self):
        return self.env.observation_spec()

    @property
    def unwrapped(self):
        return self.env.unwrapped


class ObsWrapper(Wrapper):
    def _reset(self):
        observation, info = self.env.reset()
        return self._observation(observation), info

    def _step(self, action):
        observation, reward, done, info = self.env.step(action)
        return self.observation(observation), reward, done, info

    def observation(self, observation):
        return self._observation(observation)

    def _observation(self, observation):
        raise NotImplementedError


class RewardWrapper(Wrapper):
    def _step(self, action):
        observation, reward, done, info = self.env.step(action)
        return observation, self.reward(reward), done, info

    def reward(self, reward):
        return self._reward(reward)

    def _reward(self, reward):
        raise NotImplementedError


class ActionWrapper(Wrapper):
    def _step(self, action):
        action = self.action(action)
        return self.env.step(action)

    def action(self, action):
        return self._action(action)

    def _action(self, action):
        raise NotImplementedError

    def reverse_action(self, action):
        return self._reverse_action(action)

    def _reverse_action(self, action):
        raise NotImplementedError

class MaxStepWrapper(Wrapper):
    """
        Simple wrapper to limit maximum steps of an environment
    """
    def __init__(self, env, max_steps):
        super().__init__(env)
        if max_steps <= 0:
            raise ValueError('MaxStepWrapper received max_steps')
        self.max_steps = max_steps
        self.current_step = 0

    def _reset(self):
        self.current_step = 0
        return self.env.reset()

    def _step(self, action):
        self.current_step += 1
        observation, reward, done, info = self.env.step(action)
        if self.current_step >= self.max_steps:
            done = True
        return observation, reward, done, info

# putting import inside to allow difference in dependency
class GymAdapter(Wrapper):
    def __init__(self, env):
        super().__init__(env)
        assert isinstance(env, gym.Env)

    def _reset(self):
        obs = self.env.reset()
        return obs, {}

    def observation_spec(self):
        gym_spec = self.env.observation_space
        if isinstance(gym_spec, gym.spaces.Box):
            return {
                'type': 'continuous',
                'dim': gym_spec.shape
            }
        else:
            raise ValueError('Discrete observation currently not supported')
        # TODO: migrate everything to dm_format

    def action_spec(self):
        gym_spec = self.env.action_space
        if isinstance(gym_spec, gym.spaces.Box):
            return {
                'type': 'continuous',
                'dim': gym_spec.shape
            }
        else:
            raise ValueError('Discrete observation currently not supported')
        # TODO: migrate everything to dm_format

    @property
    def spec_format(self):
        return SpecFormat.SURREAL_CLASSIC

class DMControlDummyWrapper(Wrapper):
    '''
    Dummy wrapper for deepmind control environment using pixels.  The output of
    observation_spec and action_spec will match the output for a dm_control environment
    using pixels.Wrapper().  This is used by the learner to get the action and observation
    specs without initializing a pixels wrapper.
    '''

    def __init__(self, env):
        # dm_control envs don't have metadata
        env.metadata = {}
        super().__init__(env)

    @property
    def spec_format(self):
        return SpecFormat.DM_CONTROL

    def observation_spec(self):
        return collections.OrderedDict([('pixels', dm_control.rl.specs.ArraySpec(shape=(84, 84, 3), dtype=np.dtype('uint8'), name='pixels'))])

    def action_spec(self):
        return dm_control.rl.specs.BoundedArraySpec(shape=(6,), dtype=np.dtype('float64'), name=None, minimum=[-1., -1., -1., -1., -1., -1.], maximum=[1., 1., 1., 1., 1., 1.])

class DMControlAdapter(Wrapper):
    def __init__(self, env):
        # dm_control envs don't have metadata
        env.metadata = {}
        super().__init__(env)
        self.screen = None
        assert isinstance(env, dm_control.rl.control.Environment) or \
            isinstance(env, pixels.Wrapper) or \
            isinstance(env, DMControlDummyWrapper)

    def _step(self, action):
        ts = self.env.step(action)
        reward = ts.reward
        if reward is None:
            # TODO: note that reward is none
            print('None reward')
            reward = 0
        # input is (84, 84, 3), we want (C, H, W) == (3, 84, 84)
        #print('hi', ts.observation.shape)
        #obs = ts.observation.transpose((2, 1, 0))
        #print('hi2', obs.shape)
        return ts.observation, reward, ts.step_type == StepType.LAST, {}

    def _reset(self):
        ts = self.env.reset()
        return ts.observation, {}

    def _close(self):
        self.env.close()

    @property
    def spec_format(self):
        return SpecFormat.DM_CONTROL

    def observation_spec(self):
        return collections.OrderedDict([('pixels', dm_control.rl.specs.ArraySpec(shape=(3, 84, 84), dtype=np.dtype('uint8'), name='pixels'))])
        #return self.env.observation_spec()

    def action_spec(self):
        return self.env.action_spec()

    def render(self, *args, width=480, height=480, camera_id=1, **kwargs):
        # safe for multiple calls
        pygame.init()
        if not self.screen:
            self.screen = pygame.display.set_mode((width, height))
        else:
            c_width, c_height = self.screen.get_size()
            if c_width != width or c_height != height:
                self.screen = pygame.display.set_mode((width, height))
        for event in pygame.event.get():
            if event.type == pygame.QUIT: sys.exit()

        im = self.env.physics.render(width=width, height=height, camera_id=camera_id).transpose((1,0,2))
        pygame.pixelcopy.array_to_surface(self.screen, im)
        pygame.display.update()
        return im

def flatten_obs(obs):
    flat_observations = []
    visual_observations = None
    for k, v in obs.items():
        if len(v.shape) > 1: # visual input
            # This is the desired pixel size of dm_control environments
            #print('visual shape',v.shape)
            # input is (84, 84, 3), we want (C, H, W) == (3, 84, 84)
            assert v.shape == (84, 84, 3)
            v = v.transpose((2, 1, 0))
            assert v.shape == (3, 84, 84)
            # We should only have one visual obsevations, all other items should be flat
            assert visual_observations is None
            visual_observations = v
        elif len(v.shape) == 1:
            flat_observations.append(v)
        else:
            raise Exception("Unrecognized data format")
    if len(flat_observations) == 0:
        flat_observations = None
    else:
        flat_observations = np.concatenate(flat_observations)
    return (visual_observations, flat_observations)

class ObservationConcatenationWrapper(Wrapper):
    def _step(self, action):
        #print('obs concat sub', type(self.env))
        obs, reward, done, info = self.env.step(action)
        return flatten_obs(obs), reward, done, info

    def _reset(self):
        obs, info = self.env.reset()
        return flatten_obs(obs), info

    @property
    def spec_format(self):
        return SpecFormat.SURREAL_CLASSIC

    def observation_spec(self):
        visual_dim = None
        flat_dim = 0
        #print('parent obsspec', self.env.observation_spec().items())

        for k, x in self.env.observation_spec().items():
            if len(x.shape) > 1:
                assert visual_dim is None # Should only be one visual observation
                assert x.shape == (3, 84, 84) # Expected pixel size of dm_control environments
                visual_dim = x
            elif len(x.shape) == 1:
                flat_dim += x[0]
            else:
                raise Exception("Unexpected data format")
        if flat_dim == 0:
            flat_dim = None

        return {
            'type': 'continuous',
            'dim': (visual_dim, flat_dim)
        }

    def action_spec(self):
        return {
            'type': ActionType.continuous,
            'dim': self.env.action_spec().shape,
        }
    # TODO: what about upper/lower bound information

class GrayscaleWrapper(Wrapper):
    def _grayscale(self, obs):
        obs_visual, obs_flat = obs
        if obs_visual is None:
            return obs
        C, H, W = obs_visual.shape
        assert obs_visual.shape == (3, 84, 84)
        obs_visual = np.mean(obs_visual, 0, 'uint8').reshape(1, H, W)
        return obs_visual, obs_flat

    def _step(self, action):
        obs, reward, done, info = self.env.step(action)
        obs = self._grayscale(obs)
        return obs, reward, done, info

    def _reset(self):
        obs, info = self.env.reset()
        return self._grayscale(obs), info

    @property
    def spec_format(self):
        return SpecFormat.SURREAL_CLASSIC

    def observation_spec(self):
        spec = self.env.observation_spec()
        visual_dim, flat_dim = spec['dim']
        if visual_dim is None:
            visual_dim = None
        else:
            assert visual_dim.shape == (3, 84, 84)
            C, H, W = visual_dim.shape
            visual_dim = dm_control.rl.specs.ArraySpec(shape=(1, H, W), dtype=np.dtype('uint8'), name='pixels')
        return {
            'type': 'continuous',
            'dim': (visual_dim, flat_dim)
        }

    def action_spec(self):
        return self.env.action_spec()

class FrameStackWrapper(Wrapper):
    def __init__(self, env, env_config):
        super().__init__(env)
        self.n = env_config.frame_stacks
        self._history = deque(maxlen=self.n)

    def _stacked_observation(self):
        '''
        Assumes self._history contains the last n frames from the environment
        Concatenates the frames together along the depth axis
        '''
        visual_obs = []
        flat_obs = []
        for v, f in self._history:
            visual_obs.append(v)
            flat_obs.append(f)
        if visual_obs[0] is None:
            visual_obs = None
        else:
            assert visual_obs[0].shape == (1, 84, 84) # C, H, W
            visual_obs = np.concatenate(visual_obs, axis=0)
        if flat_obs[0] is None:
            flat_obs = None
        else:
            flat_obs = flat_obs[-1] # Most recent observation
        #print(visual_obs, flat_obs)
        return (visual_obs, flat_obs)

    def _step(self, action):
        obs_next, reward, done, info = self.env.step(action)
        self._history.append(obs_next)
        obs_next_stacked = self._stacked_observation()
        return obs_next_stacked, reward, done, info

    def _reset(self):
        obs, info = self.env.reset()
        for i in range(self.n):
            self._history.append(obs)
        return self._stacked_observation(), info

    @property
    def spec_format(self):
        return SpecFormat.SURREAL_CLASSIC

    def observation_spec(self):
        spec = self.env.observation_spec()
        #print(spec)
        visual_dim, flat_dim = spec['dim']
        if visual_dim is None:
            visual_dim = None
        else:
            C, H, W = visual_dim.shape
            assert (H, W) == (84, 84)
            visual_dim = dm_control.rl.specs.ArraySpec(shape=(C * self.n, H, W), dtype=np.dtype('uint8'), name='pixels')
        return {
            'type': 'continuous', 
            'dim': (visual_dim, flat_dim)
        }

    def action_spec(self):
        return self.env.action_spec()
