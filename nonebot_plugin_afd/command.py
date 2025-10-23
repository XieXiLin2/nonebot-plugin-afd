import json
from arclet.alconna import Alconna, Args, Arparma, CommandMeta
from arclet.alconna.exceptions import SpecialOptionTriggered
from nonebot import get_bot
from nonebot.adapters.afdian import TokenBot
from nonebot.adapters.afdian.exception import ActionFailed
from nonebot.adapters.onebot.v11 import GroupMessageEvent
from nonebot.log import logger
from nonebot_plugin_alconna import AlconnaMatcher, CommandResult, on_alconna

from nonebot_plugin_afd.model import GroupAfdConfig

from .config import config_file, plugin_config, user_relation_file


def group_rule(event: GroupMessageEvent) -> bool:
    """
    处理规则，只允许配置内的群号来处理
    :param event: GroupMessageEvent
    :return: 是否同意
    """
    return event.group_id in set(plugin_config.afd_token_dict.keys())


alc = Alconna("afd", meta=CommandMeta(description="AFDian Audit Command"))  # pyright: ignore[reportUnknownVariableType]
alc_matcher = on_alconna(
    alc,
    rule=group_rule,
    aliases={"afdian"},
    skip_for_unmatch=False,
    auto_send_output=True,
    use_cmd_start=True,
)


@alc_matcher.handle()
async def _(matcher: AlconnaMatcher, res: CommandResult):
    if not res.result.error_info:
        return
    if isinstance(res.result.error_info, SpecialOptionTriggered):
        await matcher.finish(res.output)
    await matcher.finish(f"{res.result.error_info}\n使用指令 `afd -h` 查看帮助")


alc.subcommand(
    "bind",
    Args["order_id", str, "爱发电订单号"],
    help_text="绑定 AFDian 账号 (需使用所在群绑定作者的爱发电订单号)",
    alias=["b"],
)


@alc_matcher.dispatch("~bind").handle()
async def _(matcher: AlconnaMatcher, parma: Arparma, event: GroupMessageEvent):  # pyright: ignore[reportMissingTypeArgument]
    if not (author_user_id_list := plugin_config.afd_token_dict.get(event.group_id)):
        logger.warning(f"未找到群聊 {event.group_id} 的作者 user_id 配置")
        await matcher.finish("错误: 本群没有配置 AFDian 信息，不可使用绑定")

    order_id: str = parma["order_id"]

    logger.info(f"Current group user_id list: {author_user_id_list}")

    for user_id in author_user_id_list:
        logger.info(f"正在尝试获取作者 {user_id} 的 Bot")
        try:
            afdian_bot = get_bot(user_id)
            logger.info("获取 Bot 成功")
        except Exception:
            logger.warning(
                f"群聊 {event.group_id} 的 AFDianBot {user_id} 不存在，将尝试获取下一个 AFDianBot",
            )
            continue

        if not isinstance(afdian_bot, TokenBot):
            logger.warning(f"Bot {user_id} 不是爱发电 TokenBot，继续寻找")
            continue

        logger.debug(
            f"已经找到群聊 {event.group_id}，作者 {user_id} 的爱发电 Bot",
        )

        try:
            order_response = await afdian_bot.query_order_by_out_trade_no(
                out_trade_no=order_id,
            )
        except ActionFailed as e:
            logger.error(
                f"查询用户 {event.user_id} 的订单 {order_id} 出现异常，也可能该订单不属于当前 Bot，将继续使用下一个作者的 user_id 进行查询，错误信息为: {e}",
            )
            continue

        logger.debug(order_response)

        if order_response.ec != 200:
            logger.error(
                f"查询用户 {event.user_id} 的订单 {order_id} 失败，错误信息为：{order_response.em}",
            )
            logger.debug("已尝试使用下一个作者的 user_id 进行查询")
            continue
        logger.debug(f"查询用户 {event.user_id} 的订单 {order_id} 成功")

        if not order_response.data.list:
            logger.warning(
                f"查询用户 {event.user_id} 的订单 {order_id} 未找到对应订单",
            )
            await matcher.finish("错误: 未查询到订单记录")

        if len(order_response.data.list) > 1:
            logger.warning(
                f"查询用户 {event.user_id} 的订单 {order_id} 返回了多条结果",
            )
            await matcher.finish("错误: 查询到多条订单记录")

        afd_user_id = order_response.data.list[0].user_id
        logger.info(
            f"绑定用户 {event.user_id} 的爱发电账号，订单号 {order_id}，爱发电用户 ID {afd_user_id}",
        )

        current_relations: dict[int, list[str]] = json.loads(
            user_relation_file.read_text(encoding="utf-8"),
        )

        if afd_user_id in current_relations.get(event.user_id, []):
            logger.info(
                f"用户 {event.user_id} 已绑定爱发电账号，爱发电用户 ID {afd_user_id}",
            )
            await matcher.finish(f"你已绑定该爱发电账号: {afd_user_id}")

        for relation in current_relations.values():
            if afd_user_id in relation:
                logger.warning(
                    f"爱发电用户 ID {afd_user_id} 已被绑定，无法重复绑定",
                )
                await matcher.finish(
                    "错误: 该爱发电账号已被绑定，无法重复绑定，解绑请联系管理员",
                )

        current_relations[event.user_id].append(afd_user_id)

        user_relation_file.write_text(
            json.dumps(current_relations, ensure_ascii=False, indent=4),
            encoding="utf-8",
        )

        logger.info(
            f"用户 {event.user_id} 绑定爱发电账号成功，爱发电用户 ID {afd_user_id}",
        )
        await matcher.finish(f"绑定成功: {afd_user_id}")


alc.subcommand(
    "config",
    Args["key", str, "配置项键名"]["value", int | str | bool, "配置项键值"],
    help_text="配置群组信息",
    alias=["c"],
)


@alc_matcher.dispatch("~config").handle()
async def _(matcher: AlconnaMatcher, event: GroupMessageEvent, parma: Arparma):  # pyright: ignore[reportMissingTypeArgument]
    config_key: str = parma["key"]
    config_value: int | str | bool = parma["value"]

    group_id = event.group_id

    # 读取时作为普通 dict（JSON 对象的键是字符串）
    current_config: dict[str, GroupAfdConfig] = json.loads(
        config_file.read_text(encoding="utf-8"),
    )

    key = str(group_id)  # 使用字符串键与 JSON 文件保持一致
    current_group_config = current_config.get(key, GroupAfdConfig())
    # 把从文件读出的 dict 转为 BaseModel 实例，保证后续验证与赋值正确
    if isinstance(current_group_config, dict):
        try:
            model = GroupAfdConfig.model_validate(current_group_config)
        except Exception as e:
            logger.error(f"解析群配置失败: {e}")
            await matcher.finish("错误: 无法解析当前群配置文件")
    else:
        model = current_group_config

    # 校验配置项是否存在于模型字段
    model_fields = getattr(type(model), "__fields__", None)
    if model_fields is not None:
        if config_key not in model_fields:
            await matcher.finish(f"错误: 未知配置项 {config_key}")
    elif not hasattr(model, config_key):
        await matcher.finish(f"错误: 未知配置项 {config_key}")

    # 使用 BaseModel 的 copy(update=...) 做类型校验与赋值
    try:
        updated_model = model.model_copy(update={config_key: config_value})
    except Exception as e:
        logger.error(f"更新配置项 {config_key} 失败: {e}")
        await matcher.finish(f"错误: 更新配置项失败: {e}")

    # 将更新后的模型转为可序列化的 dict，后续代码会把它写回 current_config
    current_group_config = updated_model
    current_config[key] = current_group_config  # 使用字符串键写回

    config_file.write_text(
        json.dumps(current_config, ensure_ascii=False, indent=4),
        encoding="utf-8",
    )

    logger.info(
        f"群聊 {group_id} 配置项 {config_key} 已更新为 {config_value}",
    )

    await matcher.finish(f"配置项 {config_key} 已更新为 {config_value}")


alc.subcommand(
    "find",
    Args["order_id", str, "爱发电订单号"],
    help_text="查询订单号 (需使用所在群绑定作者的爱发电订单号)",
    alias=["f", "check"],
)


@alc_matcher.dispatch("~find").handle()
async def _(matcher: AlconnaMatcher, parma: Arparma, event: GroupMessageEvent):  # pyright: ignore[reportMissingTypeArgument]
    comment: str = parma["order_id"]

    logger.info(
        f"Current group user_id list: {plugin_config.afd_token_dict.get(event.group_id)}",
    )

    if not (author_user_id_list := plugin_config.afd_token_dict.get(event.group_id)):
        logger.warning(f"未找到群聊 {event.group_id} 的作者 user_id 配置")
        await matcher.finish("错误: 本群没有配置 AFDian 信息，不可使用查询")

    for user_id in author_user_id_list:
        logger.info(f"正在尝试获取作者 {user_id} 的 Bot")
        try:
            afdian_bot = get_bot(user_id)
            logger.info("获取 Bot 成功")
        except Exception:
            logger.warning(
                f"群聊 {event.group_id} 的 AFDianBot {user_id} 不存在，将尝试获取下一个 AFDianBot",
            )
            continue
        if not isinstance(afdian_bot, TokenBot):
            logger.warning(f"Bot {user_id} 不是爱发电 TokenBot，继续寻找")
            continue
        logger.debug(
            f"已经找到群聊 {event.group_id}，作者 {user_id} 的爱发电 Bot，开始查询订单",
        )
        try:
            order_response = await afdian_bot.query_order_by_out_trade_no(
                out_trade_no=comment,
            )
        except ActionFailed as e:
            logger.error(
                f"查询用户 {event.user_id} 的订单 {comment} 出现异常，也可能该订单不属于当前 Bot，将继续使用下一个作者的 user_id 进行查询，错误信息为: {e}",
            )
            continue
        logger.debug(order_response)
        if order_response.ec != 200:
            logger.error(
                f"查询用户 {event.user_id} 的订单 {comment} 失败，错误信息为：{order_response.em}",
            )
            logger.debug("已尝试使用下一个作者的 user_id 进行查询")
            continue
        logger.debug(f"查询用户 {event.user_id} 的订单 {comment} 成功")
        if not order_response.data.list:
            logger.warning(
                f"查询用户 {event.user_id} 的订单 {comment} 未找到对应订单",
            )
            await matcher.finish("错误: 未查询到订单记录")
        if len(order_response.data.list) > 1:
            logger.warning(
                f"查询用户 {event.user_id} 的订单 {comment} 返回了多条结果",
            )
            await matcher.finish("错误: 查询到多条订单记录")
        order = order_response.data.list[0]
        logger.info(
            f"查询到用户 {event.user_id} 的订单信息: 订单号 {order.out_trade_no}, 爱发电用户 ID {order.user_id}, 金额 {order.total_amount} 分, 状态 {order.status}",
        )
        await matcher.finish(
            f"查询成功:\n订单号: {order.out_trade_no}\n爱发电用户 ID: {order.user_id}\n金额: {order.total_amount} 分\n状态: {order.status}",
        )
