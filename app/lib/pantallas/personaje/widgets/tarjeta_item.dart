/// Tarjeta de ítem: la unidad visual del Vestidor (P16) y del Mercado (P15).
///
/// Un ítem poseído se muestra con el color y el brillo de su rareza; uno
/// bloqueado, en silueta con candado y con el requisito que lo abre, porque
/// saber qué falta motiva. La rareza siempre lleva su etiqueta textual: el
/// color nunca es el único portador de significado.
library;

import 'package:flutter/material.dart';

import '../../../datos/repositorios.dart';
import '../../../design/arte.dart';
import '../../../design/components.dart';
import '../../../design/theme.dart';
import '../../../design/tokens.dart';
import 'piezas.dart';

/// Tarjeta de un ítem del catálogo.
class TarjetaItem extends StatelessWidget {
  const TarjetaItem({
    required this.item,
    super.key,
    this.bloqueado = false,
    this.equipado = false,
    this.esNuevo = false,
    this.precio,
    this.puedePagar = true,
    this.motivo,
    this.alTocar,
    this.alMantener,
    this.guardando = false,
    this.seGanaAprendiendo = false,
  });

  /// Ítem del catálogo.
  final Item item;

  /// ¿Se muestra en silueta con candado?
  final bool bloqueado;

  /// ¿Está puesto ahora mismo?
  final bool equipado;

  /// Insignia "Nuevo" hasta abrir la ficha.
  final bool esNuevo;

  /// Precio en oro; `null` si no se vende.
  final int? precio;

  /// ¿Le alcanza el oro al usuario?
  final bool puedePagar;

  /// Frase de requisito ("Alcanza el nivel 5").
  final String? motivo;

  final VoidCallback? alTocar;
  final VoidCallback? alMantener;

  /// La ranura está guardándose en el servidor.
  final bool guardando;

  /// Ítem de conocimiento: no se compra, se gana aprendiendo.
  final bool seGanaAprendiendo;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final Rareza rareza = rarezaVisualDe(item.rareza);
    final Color acento = bloqueado ? p.borde : rareza.color;
    final bool quieto = reducirMovimiento(context);

    final List<String> semantica = <String>[
      item.nombre,
      rareza.etiqueta,
      nombreRanura(item.ranura),
      if (equipado) 'Equipado',
      if (bloqueado) 'Bloqueado',
      if (esNuevo) 'Nuevo',
      if (precio != null) '$precio de oro',
      ?motivo,
    ];

    return Semantics(
      label: semantica.join('. '),
      button: alTocar != null,
      excludeSemantics: true,
      child: GestureDetector(
        onLongPress: alMantener,
        child: TarjetaAtenea(
          alTocar: alTocar,
          padding: const EdgeInsets.all(Espacio.xs),
          colorBorde: acento,
          brillo: bloqueado || quieto ? 0 : rareza.brillo,
          hijo: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              Expanded(
                child: _Lienzo(
                  item: item,
                  rareza: rareza,
                  bloqueado: bloqueado,
                  equipado: equipado,
                  esNuevo: esNuevo,
                  guardando: guardando,
                ),
              ),
              const SizedBox(height: Espacio.xs),
              Text(
                item.nombre,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: context.textos.titleMedium?.copyWith(
                  color: bloqueado ? p.textoSecundario : p.textoPrimario,
                ),
              ),
              const SizedBox(height: Espacio.xxs),
              Align(
                alignment: Alignment.centerLeft,
                child: ChipRareza(rareza: rareza),
              ),
              const SizedBox(height: Espacio.xxs + 2),
              _Pie(
                precio: precio,
                puedePagar: puedePagar,
                motivo: motivo,
                bloqueado: bloqueado,
                equipado: equipado,
                seGanaAprendiendo: seGanaAprendiendo,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Lienzo extends StatelessWidget {
  const _Lienzo({
    required this.item,
    required this.rareza,
    required this.bloqueado,
    required this.equipado,
    required this.esNuevo,
    required this.guardando,
  });

  final Item item;
  final Rareza rareza;
  final bool bloqueado;
  final bool equipado;
  final bool esNuevo;
  final bool guardando;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;

    return Stack(
      fit: StackFit.expand,
      children: <Widget>[
        DecoratedBox(
          decoration: BoxDecoration(
            borderRadius: Redondeo.rChip,
            color: bloqueado
                ? p.fondo.withValues(alpha: 0.5)
                : rareza.color.withValues(alpha: 0.10),
            border: Border.all(
              color: bloqueado
                  ? p.borde
                  : rareza.color.withValues(alpha: 0.35),
            ),
          ),
          child: Center(
            child: AnimatedSwitcher(
              duration: Movimiento.corta,
              child: ImagenItem(
                key: ValueKey<String>('${item.id}-$bloqueado'),
                codigo: item.codigo,
                iconoKey: item.iconoKey,
                ranura: item.ranura,
                tamano: 56,
                color: rareza.color,
                apagado: bloqueado,
              ),
            ),
          ),
        ),
        if (rareza.brillo >= 14 && !bloqueado)
          Positioned(
            top: Espacio.xxs,
            left: Espacio.xxs,
            child: OrnamentoEsquina(color: rareza.color, tamano: 20),
          ),
        if (bloqueado)
          Align(
            alignment: Alignment.center,
            child: Icon(
              Icons.lock_rounded,
              size: 22,
              color: p.textoSecundario,
            ),
          ),
        if (esNuevo && !bloqueado)
          Positioned(
            top: Espacio.xxs,
            right: Espacio.xxs,
            child: Pildora(texto: 'Nuevo', color: p.oro),
          ),
        if (equipado)
          Positioned(
            bottom: Espacio.xxs,
            right: Espacio.xxs,
            child: Container(
              padding: const EdgeInsets.all(3),
              decoration: BoxDecoration(
                color: p.exito,
                shape: BoxShape.circle,
              ),
              child: Icon(
                Icons.check_rounded,
                size: 14,
                color: p.sobreArcano,
              ),
            ),
          ),
        if (guardando)
          Align(
            alignment: Alignment.bottomLeft,
            child: Padding(
              padding: const EdgeInsets.all(Espacio.xxs),
              child: SizedBox(
                height: 16,
                width: 16,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  color: p.arcano,
                ),
              ),
            ),
          ),
      ],
    );
  }
}

class _Pie extends StatelessWidget {
  const _Pie({
    required this.precio,
    required this.puedePagar,
    required this.motivo,
    required this.bloqueado,
    required this.equipado,
    required this.seGanaAprendiendo,
  });

  final int? precio;
  final bool puedePagar;
  final String? motivo;
  final bool bloqueado;
  final bool equipado;
  final bool seGanaAprendiendo;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;

    if (seGanaAprendiendo) {
      return Text(
        motivo ?? 'Se gana aprendiendo',
        maxLines: 2,
        overflow: TextOverflow.ellipsis,
        style: context.textos.bodySmall?.copyWith(color: p.dominio),
      );
    }

    if (equipado) {
      return Text(
        'Equipado',
        style: context.textos.bodySmall?.copyWith(
          color: p.exito,
          fontWeight: FontWeight.w700,
        ),
      );
    }

    final int? valor = precio;
    if (valor != null && !bloqueado) {
      return Row(
        children: <Widget>[
          Icon(
            Icons.monetization_on_rounded,
            size: 16,
            color: puedePagar ? p.oro : p.textoSecundario,
          ),
          const SizedBox(width: Espacio.xxs),
          Text(
            cifra(valor),
            style: Cifras.pequena(context).copyWith(
              color: puedePagar ? p.oro : p.textoSecundario,
            ),
          ),
          if (!puedePagar) ...<Widget>[
            const SizedBox(width: Espacio.xxs),
            Flexible(
              child: Text(
                'te falta oro',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: context.textos.bodySmall?.copyWith(
                  color: p.textoSecundario,
                ),
              ),
            ),
          ],
        ],
      );
    }

    return Text(
      motivo ?? 'Todavía no lo tienes',
      maxLines: 2,
      overflow: TextOverflow.ellipsis,
      style: context.textos.bodySmall?.copyWith(color: p.textoSecundario),
    );
  }
}
