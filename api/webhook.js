const { Telegraf, Markup } = require('telegraf');
const { createClient } = require('@supabase/supabase-js');

const bot = new Telegraf(process.env.BOT_TOKEN);
const supabase = createClient(process.env.SUPABASE_URL, process.env.SUPABASE_KEY);

const ADMIN_ID = 7351788975;
const userStates = {};

// ===== ГЛАВНОЕ МЕНЮ =====
const mainMenu = () => Markup.keyboard([
  ['💰 Баланс', '👥 Рефералы'],
  ['📋 Задания', '💸 Вывод'],
  ['👤 Пользователи']
]).resize();

const adminMenu = () => Markup.keyboard([
  ['➕ Добавить задание', '🗑 Удалить задание'],
  ['📢 Рассылка', '➕ Обяз канал'],
  ['🗑 Удалить обяз канал']
]).resize();

// ===== ПРОВЕРКА ПОДПИСКИ =====
async function checkSub(userId) {
  const { data } = await supabase.from('forced_channels').select('channel');
  if (!data || data.length === 0) return true;
  for (const row of data) {
    try {
      const member = await bot.telegram.getChatMember(row.channel, userId);
      if (member.status === 'left' || member.status === 'kicked') return false;
    } catch { continue; }
  }
  return true;
}

// ===== СТАРТ =====
bot.start(async (ctx) => {
  const userId = ctx.from.id;
  const args = ctx.startPayload;

  const { data: existing } = await supabase.from('users').select('*').eq('user_id', userId).single();

  if (!existing) {
    let ref = parseInt(args) || null;
    if (ref === userId) ref = null;

    await supabase.from('users').insert({ user_id: userId, referrer: ref, balance: 0 });

    if (ref) {
      await supabase.rpc('increment_balance', { uid: ref, amount: 3 });
      const { data: refUser } = await supabase.from('users').select('balance').eq('user_id', ref).single();
      try {
        await bot.telegram.sendMessage(ref,
          `🎉 По вашей реферальной ссылке зарегистрировался новый пользователь!\n\n` +
          `👤 ${ctx.from.first_name || 'Пользователь'}\n` +
          `💰 +3 ⭐ зачислено на ваш баланс\n` +
          `💼 Ваш баланс: ${refUser?.balance || 0} ⭐`
        );
      } catch {}
    }
  }

  if (!await checkSub(userId)) {
    const { data: channels } = await supabase.from('forced_channels').select('channel');
    const buttons = channels.map(c => [Markup.button.url(`📢 ${c.channel}`, `https://t.me/${c.channel.replace('@', '')}`)]);
    buttons.push([Markup.button.callback('✅ Проверить', 'check_sub')]);
    return ctx.reply('❗ Подпишись на каналы чтобы продолжить', Markup.inlineKeyboard(buttons));
  }

  await ctx.reply('✅ Добро пожаловать!', mainMenu());
});

// ===== ПРОВЕРКА ПОДПИСКИ =====
bot.action('check_sub', async (ctx) => {
  if (await checkSub(ctx.from.id)) {
    await ctx.reply('✅ Доступ открыт', mainMenu());
  } else {
    await ctx.answerCbQuery('❌ Подпишись на все каналы!', { show_alert: true });
  }
});

// ===== БАЛАНС =====
bot.hears('💰 Баланс', async (ctx) => {
  const { data } = await supabase.from('users').select('balance').eq('user_id', ctx.from.id).single();
  await ctx.reply(`💰 Баланс: ${data?.balance || 0} ⭐`);
});

// ===== ПОЛЬЗОВАТЕЛИ =====
bot.hears('👤 Пользователи', async (ctx) => {
  const { count } = await supabase.from('users').select('*', { count: 'exact', head: true });
  await ctx.reply(`👤 Всего пользователей: ${count}`);
});

// ===== РЕФЕРАЛЫ =====
bot.hears('👥 Рефералы', async (ctx) => {
  const userId = ctx.from.id;
  const { count } = await supabase.from('users').select('*', { count: 'exact', head: true }).eq('referrer', userId);
  const me = await bot.telegram.getMe();
  const link = `https://t.me/${me.username}?start=${userId}`;
  await ctx.reply(
    `👥 Твои приглашённые: ${count}\n\n💰 За каждого друга: +3 ⭐\n\n🔗 ${link}`,
    Markup.inlineKeyboard([[Markup.button.url('🚀 Пригласить друга', link)]])
  );
});

// ===== ЗАДАНИЯ =====
bot.hears('📋 Задания', async (ctx) => {
  const userId = ctx.from.id;
  const { data: tasks } = await supabase.from('tasks').select('*');
  if (!tasks || tasks.length === 0) return ctx.reply('❌ Сейчас нет доступных заданий');

  let shown = 0;
  for (const task of tasks) {
    const { data: done } = await supabase.from('completed').select('*').eq('user_id', userId).eq('task_id', task.id).single();
    if (done) continue;
    await ctx.reply(
      `📢 ${task.channel}\n💰 5 ⭐`,
      Markup.inlineKeyboard([
        [Markup.button.url('📢 Перейти', `https://t.me/${task.channel.replace('@', '')}`), Markup.button.callback('⏭ Пропустить', 'skip')],
        [Markup.button.callback('✅ Подтвердить', `check_task_${task.id}`)]
      ])
    );
    shown++;
  }
  if (shown === 0) await ctx.reply('✅ Все задания выполнены!');
});

bot.action('skip', async (ctx) => { await ctx.answerCbQuery(); });

// ===== ПРОВЕРКА ЗАДАНИЯ =====
bot.action(/check_task_(\d+)/, async (ctx) => {
  const userId = ctx.from.id;
  const taskId = parseInt(ctx.match[1]);

  const { data: task } = await supabase.from('tasks').select('*').eq('id', taskId).single();
  if (!task) return ctx.answerCbQuery('❌ Задание не найдено', { show_alert: true });

  const { data: done } = await supabase.from('completed').select('*').eq('user_id', userId).eq('task_id', taskId).single();
  if (done) return ctx.answerCbQuery('❌ Уже выполнено', { show_alert: true });

  try {
    const member = await bot.telegram.getChatMember(task.channel, userId);
    if (member.status !== 'left' && member.status !== 'kicked') {
      await supabase.rpc('increment_balance', { uid: userId, amount: 5 });
      await supabase.from('completed').insert({ user_id: userId, task_id: taskId });
      const { data: user } = await supabase.from('users').select('balance').eq('user_id', userId).single();
      await ctx.answerCbQuery('✅ +5 ⭐', { show_alert: true });
      await ctx.reply(`✅ Задание выполнено!\n\n📢 Канал: ${task.channel}\n💰 Начислено: +5 ⭐\n💼 Ваш баланс: ${user?.balance || 0} ⭐`);
    } else {
      await ctx.answerCbQuery('❌ Подпишись на канал', { show_alert: true });
    }
  } catch {
    await ctx.answerCbQuery('❌ Ошибка проверки', { show_alert: true });
  }
});

// ===== ВЫВОД =====
bot.hears('💸 Вывод', async (ctx) => {
  const { data } = await supabase.from('users').select('balance').eq('user_id', ctx.from.id).single();
  if ((data?.balance || 0) >= 100) {
    await ctx.reply('💸 Заявка отправлена');
  } else {
    await ctx.reply('❌ Минимум 100 ⭐');
  }
});

// ===== АДМИН =====
bot.command('admin', async (ctx) => {
  if (ctx.from.id !== ADMIN_ID) return;
  await ctx.reply('👑 Админ панель', adminMenu());
});

bot.hears('➕ Добавить задание', async (ctx) => {
  if (ctx.from.id !== ADMIN_ID) return;
  userStates[ctx.from.id] = 'add_task';
  await ctx.reply('Отправь канал (например @channel)');
});

bot.hears('🗑 Удалить задание', async (ctx) => {
  if (ctx.from.id !== ADMIN_ID) return;
  const { data: tasks } = await supabase.from('tasks').select('*');
  if (!tasks || tasks.length === 0) return ctx.reply('❌ Нет доступных заданий');
  const buttons = tasks.map(t => [Markup.button.callback(`🗑 #${t.id} ${t.channel}`, `del_task_${t.id}`)]);
  buttons.push([Markup.button.callback('❌ Отмена', 'admin_cancel')]);
  await ctx.reply('Выбери задание для удаления:', Markup.inlineKeyboard(buttons));
});

bot.hears('📢 Рассылка', async (ctx) => {
  if (ctx.from.id !== ADMIN_ID) return;
  userStates[ctx.from.id] = 'broadcast';
  await ctx.reply('Отправь сообщение');
});

bot.hears('➕ Обяз канал', async (ctx) => {
  if (ctx.from.id !== ADMIN_ID) return;
  userStates[ctx.from.id] = 'force';
  await ctx.reply('Отправь канал (например @channel)');
});

bot.hears('🗑 Удалить обяз канал', async (ctx) => {
  if (ctx.from.id !== ADMIN_ID) return;
  const { data: channels } = await supabase.from('forced_channels').select('channel');
  if (!channels || channels.length === 0) return ctx.reply('❌ Нет обязательных каналов');
  const buttons = channels.map(c => [Markup.button.callback(`🗑 ${c.channel}`, `del_force_${c.channel}`)]);
  buttons.push([Markup.button.callback('❌ Отмена', 'admin_cancel')]);
  await ctx.reply('Выбери канал для удаления:', Markup.inlineKeyboard(buttons));
});

// ===== КОЛЛБЭКИ УДАЛЕНИЯ =====
bot.action(/del_task_(\d+)/, async (ctx) => {
  if (ctx.from.id !== ADMIN_ID) return;
  const taskId = ctx.match[1];
  const { data: task } = await supabase.from('tasks').select('*').eq('id', taskId).single();
  if (!task) return ctx.answerCbQuery('❌ Не найдено', { show_alert: true });
  await ctx.editMessageText(`Удалить задание #${taskId} (${task.channel})?`,
    Markup.inlineKeyboard([
      [Markup.button.callback('✅ Да, удалить', `confirm_task_${taskId}`), Markup.button.callback('❌ Отмена', 'admin_cancel')]
    ])
  );
});

bot.action(/confirm_task_(\d+)/, async (ctx) => {
  if (ctx.from.id !== ADMIN_ID) return;
  const taskId = ctx.match[1];
  await supabase.from('tasks').delete().eq('id', taskId);
  await supabase.from('completed').delete().eq('task_id', taskId);
  await ctx.editMessageText(`✅ Задание #${taskId} удалено`);
});

bot.action(/del_force_(.+)/, async (ctx) => {
  if (ctx.from.id !== ADMIN_ID) return;
  const channel = ctx.match[1];
  await ctx.editMessageText(`Удалить канал ${channel}?`,
    Markup.inlineKeyboard([
      [Markup.button.callback('✅ Да, удалить', `confirm_force_${channel}`), Markup.button.callback('❌ Отмена', 'admin_cancel')]
    ])
  );
});

bot.action(/confirm_force_(.+)/, async (ctx) => {
  if (ctx.from.id !== ADMIN_ID) return;
  const channel = ctx.match[1];
  await supabase.from('forced_channels').delete().eq('channel', channel);
  await ctx.editMessageText(`✅ Канал ${channel} удалён`);
});

bot.action('admin_cancel', async (ctx) => {
  await ctx.editMessageText('❌ Отменено');
});

// ===== ТЕКСТ ОТ АДМИНА =====
bot.on('text', async (ctx) => {
  if (ctx.from.id !== ADMIN_ID) return;
  const state = userStates[ctx.from.id];

  if (state === 'add_task') {
    const { data: task } = await supabase.from('tasks').insert({ channel: ctx.message.text }).select().single();
    await ctx.reply('✅ Добавлено. Рассылаю пользователям...');
    const { data: users } = await supabase.from('users').select('user_id');
    let sent = 0;
    for (const user of users || []) {
      try {
        await bot.telegram.sendMessage(user.user_id,
          `🆕 Новое задание!\n\n📢 ${ctx.message.text}\n💰 5 ⭐`,
          Markup.inlineKeyboard([
            [Markup.button.url('📢 Перейти', `https://t.me/${ctx.message.text.replace('@', '')}`), Markup.button.callback('⏭ Пропустить', 'skip')],
            [Markup.button.callback('✅ Подтвердить', `check_task_${task.id}`)]
          ])
        );
        sent++;
      } catch {}
    }
    await ctx.reply(`📣 Задание разослано ${sent} пользователям`);

  } else if (state === 'broadcast') {
    const { data: users } = await supabase.from('users').select('user_id');
    for (const user of users || []) {
      try { await bot.telegram.sendMessage(user.user_id, ctx.message.text); } catch {}
    }
    await ctx.reply('✅ Разослано');

  } else if (state === 'force') {
    await supabase.from('forced_channels').insert({ channel: ctx.message.text });
    await ctx.reply('✅ Добавлен');
  }

  delete userStates[ctx.from.id];
});

// ===== VERCEL HANDLER =====
module.exports = async (req, res) => {
  if (req.method === 'POST') {
    await bot.handleUpdate(req.body);
    res.status(200).json({ ok: true });
  } else {
    res.status(200).send('Bot is running!');
  }
};
