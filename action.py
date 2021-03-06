import time
import logging
import random
import shutil
import os
import datetime

import cv2
import numpy as np
from adb import Adb

import config
import image_processing
import sys
import math as m


class Action():
    def __init__(self, debug: bool = False, save_mask: bool = False):
        self.adb = Adb()
        self.debug = debug
        self.save_mask = save_mask
        self.frame_index = 0

        self.forward_kick_mask = cv2.imread('templates/forward_kick_mask.png', cv2.IMREAD_GRAYSCALE)
        self.backward_kick_masks = [
            cv2.imread('templates/backward_kick_mask_1.png', cv2.IMREAD_GRAYSCALE),
            cv2.imread('templates/backward_kick_mask_2.png', cv2.IMREAD_GRAYSCALE),
        ]
        self.header_mask = cv2.imread('templates/header_mask.png', cv2.IMREAD_GRAYSCALE)

    def create_debug_dir(self):
        self.debug_dir = os.path.join('debug', f'{datetime.datetime.now():%Y%m%d%H%M%S}')
        if self.debug:
            os.makedirs(self.debug_dir, exist_ok=True)

    def match_template(
            self,
            template_path: str = None,
            coordinate: list = None,
            threshold: float = 0.8,
            color: bool = True,
            mask: bool = False,
            image: np.ndarray = None,
            diff_threshold: float = 0):

        template_image = cv2.imread(template_path)
        mask_image = cv2.imread(template_path) if mask else None

        if image is None:
            image = self.adb.get_screen()

        if coordinate:
            x = coordinate[0]
            y = coordinate[1]
            width = coordinate[2]
            height = coordinate[3]
            sub_image = image[y:y + height, x:x + width]
        else:
            sub_image = image

        score = image_processing.diff_image(
            template_image, sub_image, mask=mask_image, color=color, diff_threshold=diff_threshold)
        logging.debug(f'diff score: {score}')

        return (True, score) if score > threshold else (False, score)

    def find_template(self, template_path: str, image: np.ndarray = None):
        template_image = cv2.imread(template_path)

        if image is None:
            image = self.adb.get_screen()

        location = image_processing.find_template(image, template_image)
        logging.debug(f'Found location {location}')

        return location

    def touch_box(self, coordinate: list):
        x = coordinate[0]
        y = coordinate[1]
        width = coordinate[2]
        height = coordinate[3]

        self.adb.touch(x + width / 2, y + height / 2)

    def touch_center(self):
        self.adb.touch(config.screen_size[0] / 2, config.screen_size[1] / 2)

    def touch(self, coordinate: list):
        self.adb.touch(coordinate[0], coordinate[1])

    def swipe(self, start: list, end: list):
        self.adb.swipe(start[0], start[1], end[0], end[1], 200)

    def open_package(self):
        template_path = 'templates/free_collect.png'
        coordinate = config.free_collect_loc
        logging.info('Trying to find free collect package')
        matched, score = self.match_template(
            template_path, coordinate, mask=True)
        if matched:
            logging.info(f'Free collect package is found ({score})')
            self.touch_box(coordinate)

            logging.info('Playing video')
            time.sleep(40)

            logging.info('Finished playing video')
            self.touch(config.free_collect_end_loc)
            self.touch(config.video_package_close_loc)
            time.sleep(3)

            logging.info('Opening cards')
            self.open_cards()

        for idx in range(2):
            if idx == 0:
                template_path = 'templates/free_package_open_now.png'
                coordinate = config.package_loc
                logging.info('Trying to find large package')
            else:
                template_path = 'templates/free_package_open_now_small.png'
                coordinate = config.package_small_loc
                logging.info('Trying to find small package')

            matched, score = self.match_template(template_path, coordinate)

            if matched:
                logging.info(f'Package is found ({score})')
                self.touch_box(coordinate)
                time.sleep(3)
                self.open_cards()
                return

    def open_box(self):
        template_path = 'templates/open_now.png'
        coordinates = config.open_now_locs

        for idx, coordinate in enumerate(coordinates, start=1):
            logging.info(f'Trying to find box {idx} to open')
            matched, score = self.match_template(template_path, coordinate)

            if matched:
                logging.info(f'Found box {idx} to open ({score})')
                self.touch_box(coordinate)
                time.sleep(3)
                self.open_cards()

    def unlock_box(self):
        template_path = 'templates/tap_to_unlock.png'
        coordinates = config.tap_to_unlock_locs

        for idx, coordinate in enumerate(coordinates, start=1):
            logging.info(f'Trying to find box {idx} to unlock')
            matched, score = self.match_template(
                template_path, coordinate, threshold=0.7)

            if matched:
                logging.info(f'Found box {idx} to unlock ({score})')
                self.touch_box(coordinate)
                time.sleep(3)
                for loc in config.start_unlock_locs:
                    self.touch(loc)
                time.sleep(3)
                break

    def open_cards(self, restart_on_error=True):
        if self.sign_in():
            return False

        idx = 0
        while True:
            template_path = 'templates/okay.png'
            coordinate = config.okay_loc

            matched, score = self.match_template(template_path, coordinate)
            if matched:
                logging.info(
                    f'Found okay button to finish opening cards ({score})')
                self.touch_box(coordinate)
                break

            matched, score = self.match_template(
                'templates/upgrade.png', config.upgrade_loc)
            if matched:
                logging.info(
                    f'Player upgrade screen showed. Touch close location and going back ({score})')
                self.touch(config.close_loc)
                time.sleep(3)
                self.touch(config.go_back_loc)
                break

            matched, score = self.match_template(
                'templates/formation.png', config.formation_loc)
            if matched:
                logging.info(
                    f'Formation screen showed. Touch ok location and going back ({score})')
                self.touch(config.formation_ok_loc)
                time.sleep(3)
                self.touch(config.go_back_loc)
                break

            logging.info('Touch center since okay button is not found')
            self.touch_center()

            logging.info('Sleep 1 sec')
            time.sleep(1)

            idx += 1

            if idx > 20:
                logging.error(
                    'Can\'t find the okay button during 20 iterations')

                if restart_on_error:
                    self.adb.restart_app()
                    logging.info('App is restarted')
                    time.sleep(10)

                return False

        return True

    def kick_penalty(self):
        locations = [
            config.penalty_left_corner_loc,
            config.penalty_center_top_loc,
            config.penalty_right_corner_loc,
        ]

        loc = random.randint(0, 2)

        self.swipe(config.penalty_start_loc, locations[loc])

        location_str = ['left', 'center', 'right']
        logging.info(f'Kicked {location_str[loc]}')

    def defend_penalty(self):
        locations = [
            config.penalty_defend_left_corner_loc,
            config.penalty_defend_center_top_loc,
            config.penalty_defend_right_corner_loc,
        ]

        loc = random.randint(0, 2)

        self.adb.touch(locations[loc][0], locations[loc][1])

        location_str = ['left', 'center', 'right']
        logging.info(f'Defended {location_str[loc]}')

    def open_rewards(self):
        template_path = 'templates/claim_rewards.png'
        coordinate = config.rewards_loc
        logging.info('Trying to find rewards')

        matched, score = self.match_template(
            template_path, coordinate, mask=True)

        if matched:
            logging.info(f'Reword box is found ({score})')
            self.touch_box(coordinate)
            time.sleep(3)

            logging.info('Trying to find reward locations')
            location = self.find_template('templates/found.png')

            if location:
                logging.info('Found reward location')
                self.touch_box(location)

                logging.info('Tapped rewards')
                time.sleep(5)

                self.open_cards()

    def play_game(self):
        self.create_debug_dir()

        logging.info('Starting game')

        logging.info('Entering arena')
        self.touch(config.arena_loc)
        time.sleep(3)

        logging.info('Playing match')
        self.touch(config.play_match_loc)
        time.sleep(3)

        logging.info('Finding an opponent')
        index = 0
        while True:
            if self.sign_in():
                return

            logging.info(f'Trying to find support screen')
            matched, score = self.match_template(
                'templates/support.png', config.support_loc)
            if matched:
                logging.info(f'Connection failed. Trying again ({score})')
                self.touch(config.support_ok_loc)
                time.sleep(3)

                logging.info('Playing match')
                self.touch(config.play_match_loc)

            logging.info(f'Trying to find no opponent screen')
            matched, score = self.match_template(
                'templates/no_opponent.png', config.no_opponent_loc)
            if matched:
                logging.info(f'Connection failed. Trying again ({score})')
                self.touch(config.no_opponent_ok_loc)
                time.sleep(3)

                logging.info('Playing match')
                self.touch(config.play_match_loc)

            logging.info(f'Trying to find bid screen')
            matched, score = self.match_template(
                'templates/bid.png', config.bid_loc)
            if matched:
                logging.info(f'Bid stage ({score})')
                time.sleep(5)
                break

            index += 1

            if index > 50:
                logging.info('Something\'s wrong. Restart the app')
                self.adb.restart_app()

                return

        logging.info('Game starated')

        photo_loc = [
            0,
            0,
            config.screen_size[1],
            config.my_photo_loc[1] + config.my_photo_loc[3]
        ]

        self.frame_index = 0
        while True:
            image1 = self.adb.get_screen()

            logging.info('Trying to find game end screen')
            matched, score = self.match_template(
                'templates/game_end.png', config.game_end_loc, image=image1)
            if matched:
                logging.info(f'Game ended ({score})')
                break

            logging.info('Trying to find time out screen')
            matched, score = self.match_template(
                'templates/timeout.png', config.timeout_loc, mask=True, threshold=0.95, image=image1)
            if matched:
                logging.info(f'Timeout ({score})')
                break

            image2 = self.adb.get_screen()

            diff_image = image_processing.crop(image1, photo_loc) - image_processing.crop(image2, photo_loc)
            my_photo_diff = image_processing.crop(
                diff_image, config.my_photo_loc)
            opponent_photo_diff = image_processing.crop(
                diff_image, config.opponent_photo_loc)

            if np.sum(my_photo_diff) != 0:
                logging.info(f'{self.frame_index} My turn to kick')
                diff_score = image_processing.diff_image(image1, image2)
                logging.debug(f'frame diff score: {diff_score}')
                if diff_score < 0.5:
                    image2 = self.adb.get_screen()
                    logging.debug(f'Since frame was captured while camera is moving, re-captured')

                gray_image = cv2.cvtColor(image2, cv2.COLOR_BGR2GRAY)
                color_image = image2
 
                self.kick(gray_image, color_image)
            elif np.sum(opponent_photo_diff) != 0:
                logging.info(f'{self.frame_index} Opponent\'s turn to kick')
                #self.defend(gray_image, color_image)
            else:
                logging.info(f'{self.frame_index} In-progress')

            self.frame_index += 1

        while True:
            image = self.adb.get_screen()
            logging.info('Trying to find shootout')
            matched, score = self.match_template(
                'templates/shootout.png', config.shootout_loc, mask=True, image=image)
            if matched:
                logging.info(f'Shootout started ({score})')
                self.play_shootout()

            logging.info('Trying to find game end')
            matched, score = self.match_template(
                'templates/game_end.png', config.game_end_loc, image=image)
            if matched:
                logging.info(f'Game ended ({score})')
                self.touch_box(config.game_end_loc)
                time.sleep(3)
                break

            time.sleep(0.5)

        time.sleep(3)

        logging.info('Trying to find relagation screen')
        matched, _ = self.match_template('templates/okay.png', config.okay_loc)
        if matched:
            logging.info('Relagation. Touch okay')
            self.touch_box(config.okay_loc)
        else:
            logging.info('Trying to find promotion package screen')
            matched, _ = self.match_template(
                'templates/promotion_package.png', config.promotion_package_loc)
            if matched:
                logging.info('Promotion pakcage. Touch close')
                self.touch(config.promotion_package_close_loc)
                time.sleep(3)

            logging.info('Trying to find video watch screen')
            matched, _ = self.match_template(
                'templates/watch_video.png', config.watch_video_loc)
            if matched:
                logging.info('Accepting video package')
                self.touch_box(config.watch_video_loc)

                logging.info('Playing video for 60 secs')
                time.sleep(60)

                logging.info('Finished playing video')

                found_close_button = False
                for index, loc in enumerate(config.video_close_locs):
                    matched, _ = self.match_template(f'templates/video_close_{index}.png', loc)
                    if matched:
                        logging.info('Found close button')
                        self.touch(loc)
                        time.sleep(3)
                        found_close_button = True
                        break

                if not found_close_button:
                    logging.warning('Can\'t found video close button')
                    if self.debug:
                        cv2.imwrite(f'{self.debug_dir}\\video_error.png', self.adb.get_screen())

                    self.touch(config.free_collect_end_loc)
                    self.touch(config.video_package_close_loc)

                logging.info('Opening cards')
                if not self.open_cards():
                    return
            else:
                logging.info('There is no video watch')

        time.sleep(3)

        logging.info('Going back to the main screen')
        self.touch(config.go_back_loc)
        time.sleep(3)

    def sign_in(self):
        logging.info('Trying to find signed-out screen')
        matched, score = self.match_template(
            'templates/signed_out.png', config.signed_out_loc)
        if matched:
            logging.info('Found signed-out message. Trying to sign-in')
            self.touch(config.sign_in_loc)
            time.sleep(10)
            return True

        return False

    def shoot(self, gray_image, color_image):
        '''
        1. rgb2gray
        2. remove dashboard region
        3. 250 thresholding
        4. hough transform
        5. find upper goal post
        6. shoot to the farther corner
        '''
        logging.info('Check if it\'s shoot chance')
        gray = gray_image.copy()

        gray[0:config.dashboard_height, :] = 0
        gray[gray < 250] = 0

        lines = cv2.HoughLines(gray, 1, np.pi/180, 150)

        if lines is None or len(lines) == 0:
            logging.info('There is no goal post')
            return False

        index = 0 if len(lines) == 1 else 1
        rho, theta = sorted(lines, key=lambda x: x[0][0])[index][0]

        logging.debug(f'rho: {rho} theta: {theta}')
        if rho > 700 or theta < 0.8 or theta > 2.4:
            logging.debug('The goal post position is not valid')
            return False

        if np.sin(theta) == 0:
            logging.debug('sin(theta) == 0')
            return False

        a = -np.cos(theta) / np.sin(theta)
        b = rho / np.sin(theta)

        x1 = 0
        y1 = int(a*x1 + b)

        x2 = config.screen_size[1] - 1
        y2 = int(a*x2 + b)

        for x in range(config.screen_size[1]):
            y = int(a*x + b)
            if y < 0 or y >= config.screen_size[0]:
                continue

            if gray[y, x] > 0:
                logging.debug(f'({x}, {y}), is starting point of goal post')
                x1 = x
                y1 = y
                break

        for x in reversed(range(config.screen_size[1])):
            y = int(a*x + b)
            if y < 0 or y >= config.screen_size[0]:
                continue

            if gray[y, x] > 0:
                logging.debug(f'({x}, {y}), is ending point of goal post')
                x2 = x
                y2 = y
                break

        goal_post_length = image_processing.get_distance([x1, y1], [x2, y2])
        logging.debug(f'Goal post length: {goal_post_length}')
        if (theta > 1.4 and theta < 1.8 and goal_post_length < 170) or goal_post_length < 150:
            logging.info(f'Goal post is far ({goal_post_length}). Give up shooting')
            return False

        center = config.screen_size[1] / 2
        if abs(x1 - center) > abs(x2 - center):
            target_x = x1 + 10
        else:
            target_x = x2 - 10

        target_y = int(a*target_x + b) + 20

        if target_y > config.kick_start_loc[1]:
            logging.debug(f'It seems our goal post. Give up shooting')
            return False

        logging.info(f'Shot to ({target_x}, {target_y})')

        self.adb.swipe(
            config.kick_start_loc[0], config.kick_start_loc[1], target_x, target_y, 500)

        if self.debug:
            cv2.circle(gray, (x1, y1), 5, (128,), -1)
            cv2.circle(gray, (x2, y2), 5, (128,), -1)
            cv2.line(gray, tuple(config.kick_start_loc), (target_x, target_y), (128,), 2)

            cv2.imwrite(f'{self.debug_dir}\\shot_{self.frame_index}.png', gray)

        return True

    def kick(self, gray_image, color_image):
        if self.debug:
            cv2.imwrite(f'{self.debug_dir}\\frame_{self.frame_index}.png', color_image)

        if self.shoot(gray_image, color_image):
            return

        # if corner kick, kick to the header position
        # self.header()

        if self.kick_pass(color_image):
            return

        # random kick
        for kick in ['forward', 'backward', 'header']:
            if kick == 'forward':
                zone = [167, 420, 385, 289]
                kick_start_x = config.kick_start_loc[0]
                kick_start_y = config.kick_start_loc[1]
            elif kick == 'backward':
                zone = [0, 685, 718, 175]
                kick_start_x = config.kick_backward_start_locs[1][0]
                kick_start_y = config.kick_backward_start_locs[1][1]
            elif kick == 'header':
                zone = [215, 501, 298, 244]
                kick_start_x = config.kick_start_loc[0]
                kick_start_y = config.kick_start_loc[1]

            x = random.randint(zone[0], zone[0] + zone[2])
            y = random.randint(zone[1], zone[1] + zone[3])

            logging.info(f'Random {kick} kick from ({kick_start_x}, {kick_start_y}) to ({x}, {y})')
            self.adb.swipe(kick_start_x, kick_start_y, x, y, 500)

    def defend(self, gray_image, color_image):
        logging.debug('Implement how to defend')
        pass

    def play_shootout(self):
        logging.info('Starting shootout')

        not_found_count = 0
        while True:
            matched, score = self.match_template(
                'templates/shootout_defence.png', mask=True, threshold=0.7, diff_threshold=50)
            if (matched):
                logging.info('Found shootout defence')
                self.defend_penalty()

                time.sleep(1)
                not_found_count = 0
                continue

            matched, score = self.match_template(
                'templates/shootout_offence.png', mask=True, threshold=0.7, diff_threshold=50)
            if (matched):
                logging.info('Found shootout offence')
                self.kick_penalty()

                time.sleep(1)
                not_found_count = 0
                continue

            logging.info('None of defence and offence found')
            not_found_count += 1

            if not_found_count == 10:
                logging.info('Finished the shootout')
                break

    def kick_pass(self, image: np.ndarray):
        """Decide where to pass

        Args:
            image (np.ndarray): color image

        Returns:
            [type]: [description]
        """

        my_stats, my_centroids, op_stats, op_centroids = self.get_player_map(image)

        # preprocessing: merge into bigger location if location exists in both my and op
        my_remove_list = []
        op_remove_list = []
        for my_index, my_position in enumerate(my_centroids):
            for op_index, op_position in enumerate(op_centroids):

                horizontal_dist = abs(my_position[0] - op_position[0])
                vertial_dist = abs(my_position[1] - op_position[1])

                if horizontal_dist < 10 and vertial_dist < 20:
                    if my_stats[my_index][4] > op_stats[op_index][4]:
                        op_remove_list.append(op_index)
                    else:
                        my_remove_list.append(my_index)

        my_centroids = np.delete(my_centroids, my_remove_list, axis=0)
        op_centroids = np.delete(op_centroids, op_remove_list, axis=0)

        if self.debug:
            result = np.zeros((image.shape[0], image.shape[1], 3), np.uint8)

            for index, position in enumerate(my_centroids):
                position = tuple(map(int, position))
                cv2.circle(result, position, 10, (255, 0, 0), -1)
                cv2.putText(result, str(index), position, cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

            for index, position in enumerate(op_centroids):
                position = tuple(map(int, position))
                cv2.circle(result, position, 10, (0, 0, 255), -1)
                cv2.putText(result, str(index), position, cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

        kicks = ['forward', 'backward1', 'backward2', 'header']
        kick_found = [False, False, False, False]
        kick_masks = [
            self.forward_kick_mask, 
            self.backward_kick_masks[0],
            self.backward_kick_masks[1],
            self.header_mask
        ]
        kick_colors = [
            (0, 255, 0),    # green
            (0, 255, 255),  # yellow
            (255, 0, 255),  # magenta
            (255, 255, 0),  # cyan
        ]
        kick_start_locs = [
            config.kick_start_loc,
            config.kick_backward_start_locs[0],
            config.kick_backward_start_locs[1],
            config.header_start_loc
        ]
        kick_distance_threshold = [80, 40, 40, 60]

        for kick_index, kick in enumerate(kicks):
            for index, position in enumerate(my_centroids):
                dist = image_processing.get_distance(
                    position, kick_start_locs[kick_index])
                if dist < kick_distance_threshold[kick_index]:
                    kick_found[kick_index]= True
                    kicker_index = index
                    logging.info(f'{kick} kick ({dist})')
                    break

            if kick_found[kick_index]:
                max_dist = 0
                max_index = -1
                for my_index, my_position in enumerate(my_centroids):
                    if my_index == kicker_index:
                        continue

                    pos = list(map(int, my_position))

                    if kick_masks[kick_index][pos[1], pos[0]] == 0:
                        continue

                    min_op_dist = sys.maxsize
                    min_op_index = -1
                    for op_index, op_position in enumerate(op_centroids):
                        if (kick == 'forward' or kick == 'header') and \
                            (op_position[1] < my_position[1] or 
                            op_position[1] > my_centroids[kicker_index][1]):
                            continue

                        if (kick == 'backword1' or kick == 'backward2') and \
                            (op_position[1] > my_position[1] or 
                            op_position[1] < my_centroids[kicker_index][1]):
                            continue

                        dist = image_processing.get_point_line_distance(op_position, my_position, my_centroids[kicker_index])
                        if dist < min_op_dist:
                            min_op_dist = dist
                            min_op_index = op_index

                    logging.debug(
                        f'Minimum distance between player[{my_index}] and opponent[{min_op_index}]: {min_op_dist}')

                    if max_dist < min_op_dist:
                        max_dist = min_op_dist
                        max_index = my_index

                if max_index != -1:
                    logging.info(
                        f'Kicked to player[{max_index}]({my_centroids[max_index]}) with opponent distance {max_dist}')

                    self.swipe(kick_start_locs[kick_index], my_centroids[max_index])

                    if self.debug:
                        cv2.line(result, tuple(kick_start_locs[kick_index]), tuple(
                            map(int, my_centroids[max_index])), kick_colors[kick_index], 2)
                else:
                    logging.warning('Can\'t find proper player')
                    kick_found[kick_index] = False

        if self.debug:
            cv2.imwrite(f'{self.debug_dir}\\result_{self.frame_index}.png', result)

        if any(kick_found):
            return True
        else:
            logging.error('Can\'t find any of kick situation')
            if self.debug:
                cv2.imwrite(f'{self.debug_dir}\\error_image_{self.frame_index}.png', image)

        return False

    def get_player_map(self, image):
        image_hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        image_eh = image_processing.hsv2eh(image_hsv)

        # mask for the green playground
        playground_mask = cv2.inRange(image_eh, np.array(40, dtype=np.uint16), np.array(55, dtype=np.uint16))
        playground_mask = cv2.morphologyEx(playground_mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        playground_mask = cv2.morphologyEx(playground_mask, cv2.MORPH_CLOSE, np.ones((55, 55), np.uint8))

        my_uniform_colors = self.estimate_uniform_colors(
            image_hsv, config.my_uniform_loc)
        opponent_uniform_colors = self.estimate_uniform_colors(
            image_hsv, config.opponent_uniform_loc)

        logging.debug(
            f'my uniform color: {",".join(map(str, my_uniform_colors))}')
        logging.debug(
            f'opponent uniform color: {",".join(map(str, opponent_uniform_colors))}')

        my_mask = self.get_player_locations(image_eh, my_uniform_colors)
        opponent_mask = self.get_player_locations(
            image_eh, opponent_uniform_colors)

        # Remove non-playground region
        my_mask = cv2.bitwise_and(my_mask, playground_mask)
        opponent_mask = cv2.bitwise_and(opponent_mask, playground_mask)

        # Merge separated player's points, especially for striped uniform
        kernel = np.ones((3, 3), np.uint8)
        my_mask = cv2.morphologyEx(my_mask, cv2.MORPH_CLOSE, kernel)
        opponent_mask = cv2.morphologyEx(
            opponent_mask, cv2.MORPH_CLOSE, kernel)

        # Remove noise
        kernel = np.ones((5, 5), np.uint8)
        my_mask_open = cv2.morphologyEx(my_mask, cv2.MORPH_OPEN, kernel)
        opponent_mask_open = cv2.morphologyEx(
            opponent_mask, cv2.MORPH_OPEN, kernel)

        # Merge separated player's parts, i.e. body and leg
        kernel = np.ones((30, 30), np.uint8)
        my_mask_close = cv2.morphologyEx(my_mask_open, cv2.MORPH_CLOSE, kernel)
        opponent_mask_close = cv2.morphologyEx(
            opponent_mask_open, cv2.MORPH_CLOSE, kernel)

        _, _, my_stats, my_centroid = cv2.connectedComponentsWithStats(
            my_mask_close)
        _, _, op_stats, op_centroid = cv2.connectedComponentsWithStats(
            opponent_mask_close)

        if self.debug and self.save_mask:
            cv2.imwrite(f'{self.debug_dir}\\result_{self.frame_index}_my_mask.png', my_mask_close)
            cv2.imwrite(f'{self.debug_dir}\\result_{self.frame_index}_op_mask.png', opponent_mask_close)
            cv2.imwrite(f'{self.debug_dir}\\result_{self.frame_index}_playground_mask.png', playground_mask)
            
        # Remove the first element which covers entire screen
        return my_stats[1:], my_centroid[1:], op_stats[1:], op_centroid[1:]

    def estimate_uniform_colors(self, image_hsv, uniform_loc):
        uniform_eh = image_processing.hsv2eh(
            image_processing.crop(image_hsv, uniform_loc))
        uniform_mask = cv2.imread(
            'templates/uniform_mask.png', cv2.IMREAD_GRAYSCALE)

        uniform_masked = np.ma.masked_array(uniform_eh, uniform_mask == 0)
        values, counts = np.unique(
            uniform_masked.astype('uint16'), return_counts=True)

        uniform_pixels = np.count_nonzero(uniform_mask)

        uniform_values = []
        for v, c in zip(values, counts):
            if type(v) == np.ma.core.MaskedConstant:
                continue

            if c / uniform_pixels > 0.2:
                uniform_values.append(v)

        return uniform_values

    def get_player_locations(self, image_eh, uniform_colors):
        mask = np.zeros(image_eh.shape, np.uint8)
        for color in uniform_colors:
            if color < 180:
                if color >= 178:
                    upper_margin = 179 - color
                else:
                    upper_margin = 2

                if color <= 1:
                    lower_margin = color
                else:
                    lower_margin = 2
            else:
                if color > 240:
                    upper_margin = 255 - color
                else:
                    upper_margin = 15

                if color < 195:
                    lower_margin = color - 180
                else:
                    lower_margin = 15

            cur_mask = cv2.inRange(image_eh, np.array(
                color - lower_margin, dtype=np.uint16), np.array(color + upper_margin, dtype=np.uint16))
            mask = cv2.bitwise_or(mask, cur_mask)

        return mask
